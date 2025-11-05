from django.urls import re_path
from . import consumers

# Secure WebSocket URLs with JWT authentication
websocket_urlpatterns = [
    re_path(
        r"^ws/chat-stream/(?P<user_id>[\w-]+)/$",
        consumers.ChatStreamerConsumer.as_asgi(),
    ),
]
