from django.utils import timezone
from datetime import timedelta
from apps.tracking.models import ScreenshotWindow

WINDOW_DURATION = timedelta(minutes=10)
SCREENSHOTS_PER_WINDOW = 3

def get_or_create_active_window(time_block):
    # Check for an active window first
    window = ScreenshotWindow.objects.filter(
        time_block=time_block,
        start_at__lte=timezone.now(),
        end_at__gt=timezone.now()
    ).first()

    if window:
        return window

    # Otherwise, create next window
    last_window = ScreenshotWindow.objects.filter(time_block=time_block).order_by('-end_at').first()
    start = last_window.end_at if last_window else time_block.started_at
    end = start + WINDOW_DURATION

    return ScreenshotWindow.objects.create(
        time_block=time_block,
        start_at=start,
        end_at=end,
        expected_count=SCREENSHOTS_PER_WINDOW
    )
