import json
from django.conf import settings
from .token04_core import generate_token04

def generate_zego_token(user_id: str, room_id: str, expire_seconds: int = 3600):
    """
    Produces a valid ZEGO Token04 with both room login and publish privileges.
    """
    payload = {
        "room_id": room_id,
        "privilege": {1: 1, 2: 1},  # 1 = login, 2 = publish
        "stream_id_list": None
    }

    token_info = generate_token04(
        app_id=int(settings.APPID),
        user_id=user_id,
        secret=settings.ZEGO_SERVER_SECRET,
        effective_time_in_seconds=expire_seconds,
        payload=json.dumps(payload),
    )

    if token_info.error_code != 0:
        raise Exception(f"ZEGO token generation failed: {token_info.error_message}")

    return token_info.token
