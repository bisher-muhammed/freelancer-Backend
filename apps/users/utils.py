# apps/users/utils.py
import random
from django.core.cache import cache
from datetime import timedelta
from typing import Optional
from django. utils import timezone
from .models import UserSubscription


# import task lazily to avoid circular imports
def _get_send_task():
    try:
        from .tasks import send_otp_email  # apps.users.tasks
        return send_otp_email
    except Exception:
        return None


def generate_otp(length: int = 6) -> str:
    """
    Generate a numeric OTP of `length` digits as a string.
    Example: '034591'
    """
    if length <= 0:
        raise ValueError("length must be > 0")
    # ensure leading zeros allowed
    return "".join(str(random.randint(0, 9)) for _ in range(length))


def create_and_send_otp(
    email: str,
    purpose: str = "register",
    expiry_minutes: int = 5,
    length: int = 6,
    send_async: bool = True,
) -> str:
    """
    Generate OTP, store in cache, and send via Celery task (if available).
    Returns the OTP (useful for tests; in production you won't expose this).
    - email: recipient email
    - purpose: a namespace for OTPs (e.g., 'register', 'password_reset', ...)
    - expiry_minutes: TTL for OTP in minutes
    - length: digits in OTP
    - send_async: if False, call the send task synchronously (useful for tests)
    """
    if not email:
        raise ValueError("email is required")

    otp = generate_otp(length=length)
    print(otp)
    cache_key = f"otp:{purpose}:{email.lower().strip()}"

    # Store OTP in cache with TTL (seconds)
    cache.set(cache_key, otp, timeout=expiry_minutes * 60)

    # Trigger sending
    send_task = _get_send_task()
    if send_task:
        if send_async:
            send_task.delay(email, otp, purpose)
        else:
            # synchronous call (for tests or debug)
            send_task(email, otp, purpose)
    else:
        # If task not available, you may want to log or raise in dev
        # For now, just pass — OTP still stored in cache
        pass

    return otp


def verify_otp(email: str, otp: str, purpose: str = "register", erase: bool = True) -> bool:
    """
    Verify OTP for the given email & purpose.
    If erase=True and verification succeeds, the cached OTP will be deleted.
    """
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
