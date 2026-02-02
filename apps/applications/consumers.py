import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        print("=== WS CONNECT START ===")

        # URL params
        self.chat_id = self.scope.get("url_route", {}).get("kwargs", {}).get("chat_id")
        print("chat_id:", self.chat_id)

        self.chat_group_name = f"chat_{self.chat_id}"
        print("group:", self.chat_group_name)

        # Auth info
        user = self.scope.get("user")
        print("user:", user)
        print("is_authenticated:", getattr(user, "is_authenticated", None))

        # Permission check
        allowed = await self.is_participant()
        print("is_participant:", allowed)

        if not allowed:
            print("❌ WS REJECTED: user not participant")
            await self.close()
            return

        # Join group
        await self.channel_layer.group_add(
            self.chat_group_name,
            self.channel_name
        )
        print("✅ added to group")

        await self.accept()
        print("✅ WS ACCEPTED")

    async def disconnect(self, close_code):
        print("=== WS DISCONNECT ===", close_code)

        await self.channel_layer.group_discard(
            self.chat_group_name,
            self.channel_name
        )
        print("removed from group")

    async def receive(self, text_data):
        print("=== WS RECEIVE ===")
        print("raw:", text_data)

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            print("❌ invalid JSON")
            return

        message_content = data.get("content", "").strip()
        print("content:", message_content)

        if not message_content:
            print("❌ empty message ignored")
            return

        # Save message
        message = await self.create_message(message_content)
        print("message saved:", message.id)

        # Lazy import serializer (prevents AppRegistryNotReady)
        from apps.applications.serializers import MessageSerializer
        serialized = MessageSerializer(message).data
        print("serialized:", serialized)

        await self.channel_layer.group_send(
            self.chat_group_name,
            {
                "type": "chat_message",
                "message": serialized
            }
        )
        print("📤 broadcast sent")

    async def chat_message(self, event):
        print("=== WS SEND ===")
        print("event:", event)

        await self.send(text_data=json.dumps(event["message"]))
        print("✅ message sent to client")

    @database_sync_to_async
    def is_participant(self):
        from apps.applications.models import ChatRoom

        user = self.scope.get("user")
        print("[DB] checking participant, user:", user)

        if not user or not user.is_authenticated:
            print("[DB] ❌ unauthenticated user")
            return False

        try:
            chat = ChatRoom.objects.get(id=self.chat_id)
            print("[DB] chat found:", chat.id)
        except ChatRoom.DoesNotExist:
            print("[DB] ❌ chat not found")
            return False

        allowed = user == chat.client or user == chat.freelancer
        print("[DB] allowed:", allowed)

        return allowed

    @database_sync_to_async
    def create_message(self, content):
        from apps.applications.models import ChatRoom, Message

        user = self.scope["user"]
        chat = ChatRoom.objects.get(id=self.chat_id)

        message = Message.objects.create(
            chat_room=chat,
            sender=user,
            content=content
        )

        return message
