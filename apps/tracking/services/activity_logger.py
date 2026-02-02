from apps.tracking.models import ActivityLog

def log_activity(freelancer_profile, action, session=None, metadata=None):
    ActivityLog.objects.create(
        freelancer=freelancer_profile,
        session=session,
        action=action,
        metadata=metadata or {},
    )
