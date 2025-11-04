# Secure WebSocket Producer for LLM Response Streaming
import logging
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from datetime import datetime

logger = logging.getLogger(__name__)


class SecureFrameStreamer:
    """
    Secure WebSocket Producer for LLM Response Streaming

    This class is used by Celery tasks to send real-time updates
    to authenticated frontend clients via Django Channels WebSocket.

    Features:
    - Secure message production only (no client input accepted)
    - User-specific channel groups
    - Multiple message types (frames, responses, status, errors)
    - Proper error handling and logging
    """

    def __init__(self, user_id, chat_id=None):
        self.user_id = user_id
        self.chat_id = chat_id
        self.channel_layer = get_channel_layer()
        self.group_name = f"user_{user_id}"
        self.connected = True

        logger.info(
            f"[FrameStreamer] 📡 Initialized for user {user_id}, chat {chat_id}"
        )

    def start(self):
        """Initialize the frame streamer (compatibility method)"""
        self.connected = True
        logger.info(f"[FrameStreamer] ✅ Ready for user {self.user_id}")

    def send_processing_status(self, message="Processing your request..."):
        """Send processing status update to frontend"""
        return self._send_message(
            "send_status_update",
            {
                "status": "processing",
                "message": message,
                "chat_id": self.chat_id,
                "user_id": self.user_id,
            },
        )

    def send_frame(self, payload, chat_id=None):
        """Send frame data/progress update to frontend"""
        target_chat_id = chat_id or self.chat_id

        return self._send_message(
            "send_frame",
            {
                "frame": payload,
                "user_id": self.user_id,
                "chat_id": target_chat_id,
            },
        )

    def send_response(self, payload, chat_id=None):
        """Send final LLM response to frontend"""
        target_chat_id = chat_id or self.chat_id

        return self._send_message(
            "send_response",
            {
                "data": payload,
                "user_id": self.user_id,
                "chat_id": target_chat_id,
            },
        )

    def send_error(self, error_message, chat_id=None):
        """Send error notification to frontend"""
        target_chat_id = chat_id or self.chat_id

        return self._send_message(
            "send_error_notification",
            {
                "error": error_message,
                "user_id": self.user_id,
                "chat_id": target_chat_id,
            },
        )

    def send_status(self, status, message="", chat_id=None):
        """Send status update to frontend"""
        target_chat_id = chat_id or self.chat_id

        return self._send_message(
            "send_status_update",
            {
                "status": status,
                "message": message,
                "user_id": self.user_id,
                "chat_id": target_chat_id,
            },
        )

    def send_completion(self, chat_id=None):
        """Send task completion notification"""
        target_chat_id = chat_id or self.chat_id

        return self._send_message(
            "send_status_update",
            {
                "status": "completed",
                "message": "Response generation completed successfully",
                "user_id": self.user_id,
                "chat_id": target_chat_id,
            },
        )

    def _send_message(self, message_type, payload):
        """Internal method to send message via Django Channels"""
        if not self.connected:
            logger.warning(f"[FrameStreamer] ⚠️ Not connected. Dropping {message_type}")
            return False

        if not self.channel_layer:
            logger.error(f"[FrameStreamer] ❌ Channel layer not available")
            return False

        try:
            # Send message to the user's WebSocket group
            async_to_sync(self.channel_layer.group_send)(
                self.group_name,
                {
                    "type": message_type,
                    **payload,
                    "timestamp": datetime.now().isoformat(),
                },
            )

            logger.debug(
                f"[FrameStreamer] 🟢 {message_type} sent to user {self.user_id}"
            )
            return True

        except Exception as e:
            logger.error(f"[FrameStreamer] ❌ Error sending {message_type}: {e}")
            return False

    def stop(self):
        """Clean up the frame streamer"""
        self.connected = False
        logger.info(f"[FrameStreamer] 🔌 Stopped for user {self.user_id}")

    # === CONVENIENCE METHODS FOR COMMON LLM WORKFLOW ===

    def notify_task_started(self, prompt):
        """Notify that LLM task has started"""
        return self.send_status("started", f"Processing prompt: {prompt[:50]}...")

    def notify_llm_thinking(self):
        """Notify that LLM is processing"""
        return self.send_frame(
            {
                "status": "thinking",
                "message": "LLM is generating response...",
                "progress": "indeterminate",
            }
        )

    def notify_streaming_started(self):
        """Notify that response streaming has started"""
        return self.send_frame(
            {
                "status": "streaming",
                "message": "Response is being streamed...",
                "progress": 0,
            }
        )

    def send_partial_response(self, partial_text, progress=None):
        """Send partial response during streaming"""
        frame_data = {
            "status": "streaming",
            "partial_response": partial_text,
            "message": "Receiving response...",
        }

        if progress is not None:
            frame_data["progress"] = progress

        return self.send_frame(frame_data)

    def notify_task_completed(self, final_response):
        """Notify task completion with final response"""
        # Send final response
        success = self.send_response(
            {
                "event": "response_generated",
                "user_id": self.user_id,
                "chat_id": self.chat_id,
                "response": final_response,
                "completed_at": datetime.now().isoformat(),
            }
        )

        if success:
            # Send completion status
            self.send_completion()

        return success

    def notify_task_failed(self, error_message):
        """Notify task failure"""
        self.send_error(error_message)
        return self.send_status("failed", f"Task failed: {error_message}")


# Backward compatibility alias
FrameStreamer = SecureFrameStreamer
