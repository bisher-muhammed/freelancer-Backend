
from apps.notifications.models import ActivityLog

def log_activity(*, activity_type, description, actor=None, metadata=None):
    ActivityLog.objects.create(
        activity_type=activity_type,
        description=description,
        actor=actor,
        metadata=metadata or {},
    )
