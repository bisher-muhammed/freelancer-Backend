import time
import jwt
from django.conf import settings


def generate_zego_token(user_id: str, room_id: str, can_publish=True, expire_seconds=3600):
    now = int(time.time())

    privilege = {
        "1": 1,  # login room
        "2": 1 if can_publish else 0,  # publish stream
    }

    payload = {
        "app_id": settings.APPID,
        "user_id": user_id,
        "room_id": room_id,
        "privilege": privilege,
        "iat": now,
        "exp": now + expire_seconds,
    }

    return jwt.encode(
        payload,
        settings.ZEGO_SERVER_SECRET,
        algorithm="HS256",
    )
