import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)

# Keep in line with what the chat UI can reasonably render
MAX_MESSAGE_LENGTH = 5000


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        # URL params
        self.chat_id = self.scope.get("url_route", {}).get("kwargs", {}).get("chat_id")
        self.chat_group_name = f"chat_{self.chat_id}"

        # Permission check
        allowed = await self.is_participant()

        if not allowed:
            logger.debug("Chat WS rejected for chat %s", self.chat_id)
            await self.close()
            return

        # Join group
        await self.channel_layer.group_add(
            self.chat_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.chat_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        if not isinstance(data, dict):
            return

        content = data.get("content", "")
        if not isinstance(content, str):
            return

        message_content = content.strip()

        if not message_content or len(message_content) > MAX_MESSAGE_LENGTH:
            return

        # Save message
        message = await self.create_message(message_content)
        if message is None:
            return

        # Lazy import serializer (prevents AppRegistryNotReady)
        from apps.applications.serializers import MessageSerializer
        serialized = MessageSerializer(message).data

        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                "type": "chat_message",
                "message": serialized
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event["message"], default=str))

    @database_sync_to_async
    def is_participant(self):
        from apps.applications.models import ChatRoom

        user = self.scope.get("user")

        if not user or not user.is_authenticated:
            return False

        try:
            chat = ChatRoom.objects.get(id=self.chat_id)
        except ChatRoom.DoesNotExist:
            return False

        return user == chat.client or user == chat.freelancer

    @database_sync_to_async
    def create_message(self, content):
        from apps.applications.models import ChatRoom, Message

        user = self.scope["user"]
        chat = ChatRoom.objects.filter(id=self.chat_id).first()
        if chat is None or not chat.is_active:
            return None

        return Message.objects.create(
            chat_room=chat,
            sender=user,
            content=content
        )
