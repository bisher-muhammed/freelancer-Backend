# apps/applications/routing.py
from django.urls import re_path, path
from apps.applications.consumers import ChatConsumer
from apps.notifications.consumers import NotificationConsumer

websocket_urlpatterns = [
    # Chat
    re_path(r"ws/chat/(?P<chat_id>\d+)/$", ChatConsumer.as_asgi()),

    # Notifications
    path("ws/notifications/", NotificationConsumer.as_asgi()),
]
