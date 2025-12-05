# apps/users/tasks.py
from celery import shared_task
from django.core.mail import send_mail
from django.conf import settings

@shared_task
def send_otp_email(email: str, otp: str, purpose: str = "register"):
    subject = f"[YourApp] OTP for {purpose}"
    message = f"Your verification code is {otp}. It will expire in 5 minutes."
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    send_mail(subject, message, from_email, [email])
