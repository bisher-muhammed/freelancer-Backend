
from celery import shared_task
from django.utils import timezone
from apps.applications.models import Meeting
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.core.mail import EmailMessage
from django.conf import settings
from apps.applications.models import Offer


@shared_task(bind=True, autoretry_for=(Exception,), retry_kwargs={"max_retries": 3})
def mark_no_show_meetings(self):
    now = timezone.now()

    updated = Meeting.objects.filter(
        status="scheduled",
        end_time__lt=now
    ).update(
        status="no_show"
    )

    return updated



from zoneinfo import ZoneInfo
from django.conf import settings
from django.template.loader import render_to_string
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.utils.timezone import localtime
from celery import shared_task
from apps.applications.models import Meeting

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def send_meeting_created_email(self, meeting_id):
    """
    Send meeting confirmation email to both client and freelancer.
    Datetimes are converted to each user's last detected timezone.
    """
    try:
        meeting = (
            Meeting.objects
            .select_related(
                "proposal",
                "proposal__project",
                "proposal__project__client",
                "proposal__freelancer",
            )
            .get(id=meeting_id)
        )
    except Meeting.DoesNotExist:
        
        return

    recipients = [
        meeting.proposal.project.client,
        meeting.proposal.freelancer,
    ]

    for user_obj in recipients:
        try:
            # 1️⃣ Determine the correct timezone
            tz_name = (
                getattr(user_obj, "last_detected_timezone", None) or
                getattr(user_obj, "timezone", None) or
                settings.TIME_ZONE
            )
            user_tz = ZoneInfo(tz_name)
            

            # 2️⃣ Convert meeting times to user's local timezone
            local_start = localtime(meeting.start_time, user_tz)
            local_end = localtime(meeting.end_time, user_tz)
            

            # 3️⃣ Prepare names and email context
            freelancer_user = meeting.proposal.freelancer
            client_user = meeting.proposal.project.client

            context = {
                "meeting": meeting,
                "user": user_obj,
                "start_time": local_start,
                "end_time": local_end,
                "timezone_name": tz_name,
                "freelancer_name": freelancer_user.get_full_name() or freelancer_user.username,
                "client_name": client_user.get_full_name() or client_user.username,
                "portal_url": f"{settings.SITE_URL}/meetings/{meeting.id}/",
            }

            # 4️⃣ Subject line with local time
            subject = (
                f"Meeting Scheduled · "
                f"{local_start.strftime('%d %b %Y, %I:%M %p')} "
                f"({tz_name})"
            )

            # 5️⃣ Render HTML and plain text email content
            html_content = render_to_string("emails/meeting_scheduled.html", context)
            text_content = strip_tags(html_content)

            # 6️⃣ Send email
            msg = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user_obj.email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send()

            

        except Exception as e:
            
            raise e




@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=10,
    retry_kwargs={"max_retries": 3},
)
def send_offer_created_email(self, offer_id):
    try:
        offer = (
            Offer.objects
            .select_related(
                "proposal",
                "proposal__project",
                "client",
                "freelancer",
            )
            .get(id=offer_id)
        )
    except Offer.DoesNotExist:
        return

    freelancer = offer.freelancer
    client = offer.client
    project = offer.proposal.project

    # 1️⃣ Resolve freelancer timezone
    tz_name = (
        getattr(freelancer, "last_detected_timezone", None)
        or getattr(freelancer, "timezone", None)
        or settings.TIME_ZONE
    )
    user_tz = ZoneInfo(tz_name)

    valid_until_local = (
        localtime(offer.valid_until, user_tz)
        if offer.valid_until else None
    )

    # 2️⃣ Email context (NO URL)
    context = {
        "freelancer_name": freelancer.get_full_name() or freelancer.username,
        "client_name": client.get_full_name() or client.username,
        "project_title": project.title,
        "rate_type": offer.rate_type.capitalize(),
        "rate": (
            offer.fixed_rate
            if offer.rate_type == "fixed"
            else offer.hourly_rate
        ),
        "valid_until": valid_until_local,
        "timezone_name": tz_name,
        "message": offer.message,
    }

    subject = f"New Offer Received · {project.title}"

    html_content = render_to_string(
        "emails/offer_created.html",
        context
    )

    email = EmailMessage(
        subject=subject,
        body=html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[freelancer.email],
    )
    email.content_subtype = "html"
    email.send()
