import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


def _push(recipient_id, payload):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(f"user_{recipient_id}", payload)
    except Exception:
        # Realtime delivery is best effort; the DB row is the source of truth
        # and the client re-fetches /notifications/. A Redis outage must not
        # fail (and roll back) the business operation that notified.
        logger.warning("Realtime notification push failed", exc_info=True)


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

    payload = {
        "type": "send_notification",
        "id": notif.id,
        "title": title,
        "message": message,
        "notif_type": notif_type,
        "data": data,
        "created_at": str(notif.created_at),
        "is_read": False,
    }

    # ✅ Push via WebSocket once the surrounding transaction commits, so
    # clients never see a notification for work that was rolled back.
    recipient_id = recipient.id
    transaction.on_commit(lambda: _push(recipient_id, payload))

    return notif
