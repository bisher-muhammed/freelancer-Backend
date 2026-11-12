# apps/users/utils.py
import logging
import secrets
from django.core.cache import cache

# ✅ Direct import (NO lazy import)
from apps.users.tasks import send_otp_email

logger = logging.getLogger(__name__)

# Wrong guesses allowed before an OTP is invalidated (brute-force guard).
MAX_OTP_ATTEMPTS = 5

# One-time token issued after a password-reset OTP is verified.
PASSWORD_RESET_TOKEN_TTL_SECONDS = 10 * 60


def _otp_key(purpose: str, email: str) -> str:
    return f"otp:{purpose}:{email.lower().strip()}"


def _otp_attempts_key(purpose: str, email: str) -> str:
    return f"otp_attempts:{purpose}:{email.lower().strip()}"


def generate_otp(length: int = 6) -> str:
    if length <= 0:
        raise ValueError("length must be > 0")
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


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

    # Store OTP in cache and reset the failed-attempt counter
    cache.set(_otp_key(purpose, email), otp, timeout=expiry_minutes * 60)
    cache.delete(_otp_attempts_key(purpose, email))

    # ✅ ALWAYS call task (no silent skip). Never log the OTP itself.
    try:
        if send_async:
            send_otp_email.delay(email, otp, purpose)
        else:
            send_otp_email(email, otp, purpose)
    except Exception:
        logger.exception("Failed to send %s OTP email", purpose)
        raise

    return otp


def verify_otp(email: str, otp: str, purpose: str = "register", erase: bool = True) -> bool:
    if not email or not otp:
        return False

    cache_key = _otp_key(purpose, email)
    cached = cache.get(cache_key)

    if cached is None:
        return False

    if secrets.compare_digest(str(cached), str(otp).strip()):
        if erase:
            cache.delete(cache_key)
            cache.delete(_otp_attempts_key(purpose, email))
        return True

    # Wrong guess: burn the OTP after too many attempts
    attempts_key = _otp_attempts_key(purpose, email)
    cache.add(attempts_key, 0, timeout=15 * 60)
    try:
        attempts = cache.incr(attempts_key)
    except ValueError:
        attempts = MAX_OTP_ATTEMPTS
    if attempts >= MAX_OTP_ATTEMPTS:
        cache.delete(cache_key)
        cache.delete(attempts_key)

    return False


def _reset_token_key(email: str) -> str:
    return f"pwreset_token:{email.lower().strip()}"


def issue_password_reset_token(email: str) -> str:
    """Single-use token proving the reset OTP was verified."""
    token = secrets.token_urlsafe(32)
    cache.set(_reset_token_key(email), token, timeout=PASSWORD_RESET_TOKEN_TTL_SECONDS)
    return token


def consume_password_reset_token(email: str, token: str) -> bool:
    if not email or not token:
        return False
    key = _reset_token_key(email)
    cached = cache.get(key)
    if cached is None or not secrets.compare_digest(str(cached), str(token)):
        return False
    cache.delete(key)
    return True
