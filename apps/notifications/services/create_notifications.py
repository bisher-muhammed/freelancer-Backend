from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from apps.notifications.models import Notification


def notify_user(recipient, notif_type, title, message="", data=None):

    if data is None:
        data = {}

    # ✅ Save in DB
    notif = Notification.objects.create(
        recipient=recipient,
        notif_type=notif_type,
        title=title,
        message=message,
        data=data
    )

    # ✅ Push instantly via WebSocket
    channel_layer = get_channel_layer()

    async_to_sync(channel_layer.group_send)(
    f"user_{recipient.id}",
    {
        "type": "send_notification",
        "id": notif.id,
        "title": title,
        "message": message,
        "notif_type": notif_type,
        "data": data,
        "created_at": str(notif.created_at),
        "is_read": False,
    }
)


    return notif
