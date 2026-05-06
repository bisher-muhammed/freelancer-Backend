# apps/users/utils.py
import random
from django.core.cache import cache
from django.utils import timezone
from typing import Optional
from .models import UserSubscription

# ✅ Direct import (NO lazy import)
from apps.users.tasks import send_otp_email


def generate_otp(length: int = 6) -> str:
    if length <= 0:
        raise ValueError("length must be > 0")
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def create_and_send_otp(
    email: str,
    purpose: str = "register",
    expiry_minutes: int = 5,
    length: int = 6,
    send_async: bool = True,
) -> str:
    if not email:
        raise ValueError("email is required")

    otp = generate_otp(length=length)
    print("Generated OTP:", otp)

    cache_key = f"otp:{purpose}:{email.lower().strip()}"

    # Store OTP in cache
    cache.set(cache_key, otp, timeout=expiry_minutes * 60)

    # ✅ ALWAYS call task (no silent skip)
    try:
        if send_async:
            print("CALLING CELERY TASK", email, otp)
            send_otp_email.delay(email, otp, purpose)
        else:
            print("CALLING SYNC EMAIL", email, otp)
            send_otp_email(email, otp, purpose)
    except Exception as e:
        # ✅ Don’t hide errors anymore
        print("ERROR SENDING OTP:", str(e))
        raise e

    return otp


def verify_otp(email: str, otp: str, purpose: str = "register", erase: bool = True) -> bool:
    if not email or not otp:
        return False

    cache_key = f"otp:{purpose}:{email.lower().strip()}"
    cached = cache.get(cache_key)

    if cached is None:
        return False

    if str(cached) == str(otp):
        if erase:
            cache.delete(cache_key)
        return True

    return False




def expire_old_subscriptions(user):
        now = timezone.now()
        active_subs = UserSubscription.objects.filter(user=user, is_active=True)
        for sub in active_subs:
            if sub.end_date and sub.end_date < now:
                sub.is_active = False
                sub.save(update_fields=["is_active"])
