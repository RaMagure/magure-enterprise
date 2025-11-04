import json
import logging
from datetime import datetime, timedelta
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from users.models import UserProfile

logger = logging.getLogger(__name__)


class FrameStreamerConsumer(AsyncWebsocketConsumer):
    """
    Secure Producer-Only WebSocket Consumer

    This consumer only receives messages from the server (via Celery tasks)
    and sends them to authenticated frontend clients. It doesn't accept
    messages from clients except for connection health checks.

    Security Features:
    - JWT Authentication required
    - User authorization (can only connect to own channel)
    - Rate limiting on connections
    - Origin verification (CORS protection)
    - Connection tracking and limits
    """

    # Security settings
    MAX_CONNECTIONS_PER_USER = 3
    CONNECTION_TIMEOUT = timedelta(hours=2)

    async def connect(self):
        """Secure WebSocket connection with JWT authentication"""

        # Extract and validate authentication token
        token = await self.get_auth_token()
        if not token:
            logger.warning(
                f"WebSocket connection rejected: No authentication token from {self.get_client_ip()}"
            )
            await self.close(code=4001)  # Unauthorized
            return

        # Authenticate user using JWT
        self.user = await self.authenticate_user(token)
        if not self.user or isinstance(self.user, AnonymousUser):
            logger.warning(
                f"WebSocket connection rejected: Invalid authentication from {self.get_client_ip()}"
            )
            await self.close(code=4001)  # Unauthorized
            return

        # Extract user_id from URL and validate authorization
        self.user_id = self.scope.get("url_route", {}).get("kwargs", {}).get("user_id")
        if not self.user_id:
            logger.warning("WebSocket connection rejected: No user_id in URL")
            await self.close(code=4000)  # Bad Request
            return

        # Authorization: Ensure user can only connect to their own channel
        if str(self.user.user_id) != self.user_id:
            logger.warning(
                f"WebSocket authorization failed: User {self.user.user_id} tried to access {self.user_id}"
            )
            await self.close(code=4003)  # Forbidden
            return

        # Check connection limits per user
        if not await self.check_connection_limits():
            logger.warning(
                f"WebSocket connection rejected: Too many connections for user {self.user_id}"
            )
            await self.close(code=4429)  # Too Many Requests
            return

        # Verify request origin for CORS protection
        if not self.verify_origin():
            logger.warning(
                f"WebSocket connection rejected: Invalid origin from {self.get_client_ip()}"
            )
            await self.close(code=4403)  # Forbidden
            return

        # Setup user group for message broadcasting
        self.group_name = f"user_{self.user_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # Track this connection
        await self.track_connection()

        # Accept the connection
        await self.accept()

        # Send connection confirmation
        await self.send_system_message("connected", "WebSocket connection established")

        logger.info(
            f"[WebSocket] ✅ Secure connection established for user {self.user_id} from {self.get_client_ip()}"
        )

    async def disconnect(self, code):
        """Clean disconnect with proper tracking cleanup"""
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

        if hasattr(self, "user_id"):
            await self.untrack_connection()

        logger.info(
            f"[WebSocket] 🔌 User {getattr(self, 'user_id', 'unknown')} disconnected (code: {code})"
        )

    async def receive(self, text_data=None, bytes_data=None):
        """
        Handle received WebSocket messages from client (LIMITED)

        This is a producer-only WebSocket, so we only accept:
        - Ping messages for connection health checks
        - Authentication refresh (optional)
        """
        if not hasattr(self, "user_id"):
            await self.close(code=4001)  # Unauthorized
            return

        if text_data:
            try:
                # Limit message size to prevent abuse
                if len(text_data) > 512:  # 512 bytes max for ping/health checks
                    await self.send_error("Message too large")
                    return

                text_data_json = json.loads(text_data)
                message_type = text_data_json.get("type")

                if message_type == "ping":
                    await self.handle_ping(text_data_json)
                elif message_type == "heartbeat":
                    await self.handle_heartbeat()
                else:
                    # This is producer-only, reject other message types
                    await self.send_error(
                        f"Message type '{message_type}' not supported in producer-only mode"
                    )

            except json.JSONDecodeError:
                await self.send_error("Invalid JSON format")
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                await self.send_error("Message processing error")

    # === PRODUCER METHODS (Called by Celery tasks) ===

    async def send_frame(self, event):
        """Send frame update to frontend (called by Celery task)"""
        if not await self.validate_producer_event(
            event, ["frame", "user_id", "chat_id"]
        ):
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "llm_frame",
                    "user_id": event["user_id"],
                    "chat_id": event["chat_id"],
                    "frame": event["frame"],
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
        logger.debug(
            f"Frame sent to user {event['user_id']} for chat {event['chat_id']}"
        )

    async def send_response(self, event):
        """Send final LLM response to frontend (called by Celery task)"""
        if not await self.validate_producer_event(
            event, ["data", "user_id", "chat_id"]
        ):
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "llm_response",
                    "user_id": event["user_id"],
                    "chat_id": event["chat_id"],
                    "data": event["data"],
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
        logger.info(
            f"Final response sent to user {event['user_id']} for chat {event['chat_id']}"
        )

    async def send_error_notification(self, event):
        """Send error notification to frontend (called by Celery task)"""
        if not await self.validate_producer_event(
            event, ["error", "user_id", "chat_id"]
        ):
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "llm_error",
                    "user_id": event["user_id"],
                    "chat_id": event["chat_id"],
                    "error": event["error"],
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )
        logger.warning(
            f"Error notification sent to user {event['user_id']} for chat {event['chat_id']}: {event['error']}"
        )

    async def send_status_update(self, event):
        """Send status update to frontend (called by Celery task)"""
        if not await self.validate_producer_event(
            event, ["status", "user_id", "chat_id"]
        ):
            return

        await self.send(
            text_data=json.dumps(
                {
                    "type": "llm_status",
                    "user_id": event["user_id"],
                    "chat_id": event["chat_id"],
                    "status": event["status"],
                    "message": event.get("message", ""),
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

    # === HELPER METHODS ===

    async def handle_ping(self, data):
        """Handle ping message for connection health"""
        timestamp = data.get("timestamp", datetime.now().isoformat())
        await self.send(
            text_data=json.dumps(
                {
                    "type": "pong",
                    "timestamp": timestamp,
                    "server_time": datetime.now().isoformat(),
                    "user_id": self.user_id,
                }
            )
        )

    async def handle_heartbeat(self):
        """Handle heartbeat to keep connection alive"""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "heartbeat_ack",
                    "timestamp": datetime.now().isoformat(),
                    "status": "connected",
                }
            )
        )

    async def send_system_message(self, status, message):
        """Send system message to client"""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "system",
                    "status": status,
                    "message": message,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

    async def send_error(self, message):
        """Send error message to client"""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "message": message,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        )

    # === SECURITY METHODS ===

    async def get_auth_token(self):
        """Extract JWT token from WebSocket headers or query params"""
        # Check query parameters first (most common for WebSocket)
        query_string = self.scope.get("query_string", b"").decode("utf-8")
        if "token=" in query_string:
            for param in query_string.split("&"):
                if param.startswith("token="):
                    return param.split("token=")[1]

        # Check Authorization header (if supported by WebSocket client)
        headers = dict(self.scope.get("headers", []))
        auth_header = headers.get(b"authorization")
        if auth_header:
            try:
                auth_type, token = auth_header.decode().split(" ", 1)
                if auth_type.lower() == "bearer":
                    return token
            except (ValueError, UnicodeDecodeError):
                pass

        return None

    @database_sync_to_async
    def authenticate_user(self, token):
        """Authenticate user using JWT token"""
        try:
            access_token = AccessToken(token)
            user_id = access_token.get("user_id")
            user = UserProfile.objects.get(user_id=user_id)
            return user
        except (InvalidToken, TokenError, UserProfile.DoesNotExist) as e:
            logger.warning(f"Authentication failed: {e}")
            return AnonymousUser()

    def verify_origin(self):
        """Verify WebSocket origin for CORS protection"""
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]

        headers = dict(self.scope.get("headers", []))
        origin_header = headers.get(b"origin")

        if origin_header:
            origin = origin_header.decode()
            return origin in allowed_origins

        return True  # Allow same-origin requests

    async def check_connection_limits(self):
        """Check if user has exceeded connection limits"""
        connection_key = f"ws_connections:{self.user_id}"
        current_connections = cache.get(connection_key, 0)
        return current_connections < self.MAX_CONNECTIONS_PER_USER

    async def track_connection(self):
        """Track user connection"""
        connection_key = f"ws_connections:{self.user_id}"
        timeout = int(self.CONNECTION_TIMEOUT.total_seconds())
        current = cache.get(connection_key, 0)
        cache.set(connection_key, current + 1, timeout)

    async def untrack_connection(self):
        """Remove connection tracking"""
        connection_key = f"ws_connections:{self.user_id}"
        current = cache.get(connection_key, 0)
        if current > 0:
            cache.set(connection_key, current - 1, 300)
        else:
            cache.delete(connection_key)

    def get_client_ip(self):
        """Get client IP address for logging"""
        headers = dict(self.scope.get("headers", []))

        # Check for forwarded IP (if behind proxy)
        forwarded_for = headers.get(b"x-forwarded-for")
        if forwarded_for:
            return forwarded_for.decode().split(",")[0].strip()

        # Check real IP header
        real_ip = headers.get(b"x-real-ip")
        if real_ip:
            return real_ip.decode()

        # Fall back to direct client IP
        return self.scope.get("client", ["unknown", 0])[0]

    async def validate_producer_event(self, event, required_fields):
        """Validate event data from Celery producer"""
        if not isinstance(event, dict):
            logger.error("Producer event is not a dictionary")
            return False

        for field in required_fields:
            if field not in event:
                logger.error(f"Producer event missing required field: {field}")
                return False

        # Validate user_id matches connection
        if event.get("user_id") != self.user_id:
            logger.warning(
                f"Producer event user_id mismatch: expected {self.user_id}, got {event.get('user_id')}"
            )
            return False

        return True
