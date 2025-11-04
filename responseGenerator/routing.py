from django.urls import re_path
from . import consumers

# Secure WebSocket URLs with JWT authentication
websocket_urlpatterns = [
    re_path(
        r"^ws/frame-stream/(?P<user_id>\w+)/$",
        consumers.FrameStreamerConsumer.as_asgi(),
    ),
]
