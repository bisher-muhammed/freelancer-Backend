import json
from channels.generic.websocket import AsyncWebsocketConsumer


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):

        user = self.scope["user"]

        if user.is_anonymous:
            await self.close()
            return

        self.group_name = f"user_{user.id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):

        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def send_notification(self, event):

        await self.send(text_data=json.dumps({
            "id": event.get("id"),
            "title": event["title"],
            "message": event["message"],
            "notif_type": event["notif_type"],
            "data": event["data"],
            "created_at": event.get("created_at"),
        }))
