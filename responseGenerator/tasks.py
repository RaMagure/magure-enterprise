from celery import shared_task
from responseGenerator.LLM import LLM
from .utils import send_webhook
from .chatStreamer import ChatStreamer
from django.conf import settings
from datetime import datetime
import redis
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def generate_response(self, prompt, llm, chat_id, user_id):
    """
    Secure LLM Response Generation Task

    This task processes LLM prompts and sends real-time updates
    to authenticated frontend clients via secure WebSocket.

    Args:
        prompt: User input prompt
        llm: LLM configuration object
        chat_id: Chat session identifier
        user_id: Authenticated user identifier
    """

    # Initialize secure WebSocket producer
    streamer = ChatStreamer(user_id, chat_id)
    streamer.start()

    # Redis connection for task tracking
    r = redis.from_url(settings.CELERY_BROKER_URL, decode_responses=True)

    try:
        # Notify task started
        streamer.notify_task_started(prompt)

        # Initialize LLM instance
        llm_instance = LLM(
            api_key=llm["llm_object"]["api_key"],
            selected_model=llm["llm_object"]["selected_model"],
        )

        # Notify LLM thinking phase
        streamer.notify_llm_thinking()

        # Generate response
        response_text = llm_instance.chat(prompt)

        # Prepare final response payload
        response_payload = {
            "event": "response_generated",
            "user_id": user_id,
            "chat_id": chat_id,
            "data": {
                "prompt": prompt,
                "response": response_text,
                "model": llm["llm_object"]["selected_model"],
                "timestamp": datetime.now().isoformat(),
            },
        }
        print("Response Payload:", response_payload)
        # Send final response via WebSocket
        if streamer.notify_task_completed(response_text):
            logger.info(
                f"[Celery] Response sent successfully to user {user_id} for chat {chat_id}"
            )
        else:
            logger.warning(f"[Celery] Failed to send response to user {user_id}")

        # Optional: Send webhook notification if configured
        webhook_url = getattr(settings, "WEBHOOK_URL", None)
        if webhook_url:
            try:
                send_webhook(webhook_url, response_payload)
                logger.info(f"[Celery] Webhook sent successfully for chat {chat_id}")
            except Exception as webhook_error:
                logger.error(
                    f"[Celery] Webhook failed for chat {chat_id}: {webhook_error}"
                )

        return {
            "status": "success",
            "user_id": user_id,
            "chat_id": chat_id,
            "response_length": len(response_text),
            "model": llm["llm_object"]["selected_model"],
        }

    except Exception as e:
        error_message = f"LLM processing failed: {str(e)}"
        logger.error(f"[Celery] {error_message} for user {user_id}, chat {chat_id}")

        # Send error notification via WebSocket
        streamer.notify_task_failed(error_message)

        # Re-raise for Celery error handling
        raise

    finally:
        # Cleanup
        logger.info(f"[Celery] Cleaning up task for user {user_id}")

        # Remove task tracking
        try:
            r.delete(f"stop_task_{self.request.id}")
        except Exception as redis_error:
            logger.warning(f"[Celery] Redis cleanup failed: {redis_error}")

        # Stop the streamer
        streamer.stop()

        logger.info(f"[Celery] Task completed for user {user_id}, chat {chat_id}")
