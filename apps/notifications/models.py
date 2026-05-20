from django.db import models
from django.conf import settings



class Notification(models.Model):
    """
    Universal notification model for Client, Freelancer, Admin.
    """

    NOTIFICATION_TYPES = [
        ("PROJECT_CREATED", "Project Created"),
        ("PROPOSAL_SUBMITTED", "Proposal Submitted"),
        ("OFFER_SENT", "Offer Sent"),
        ("OFFER_ACCEPTED", "Offer Accepted"),
        ("CONTRACT_CREATED", "Contract Created"),
        ("PAYMENT_COMPLETED", "Payment Completed"),
        ("PROFILE_UPDATED", "Profile Updated"),
        ("SYSTEM", "System Notification"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )

    notif_type = models.CharField(
        max_length=50,
        choices=NOTIFICATION_TYPES
    )

    title = models.CharField(max_length=255)

    message = models.TextField(blank=True)

    data = models.JSONField(default=dict, blank=True)

    # Status flags
    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]
        

    def __str__(self):
        return f"Notification({self.recipient.username}, {self.notif_type})"




class ActivityLog(models.Model):
    """
    Immutable system-wide activity log.
    Used for admin dashboards, audits, timelines.
    """

    ACTIVITY_TYPES = [
        ("USER_REGISTERED", "User Registered"),
        ("PROJECT_CREATED", "Project Created"),
        ("PAYMENT_PROCESSED", "Payment Processed"),
        ("ESCROW_FUNDED", "Escrow Funded"),
        ("ESCROW_RELEASED", "Escrow Released"),
        ("ESCROW_REFUNDED", "Escrow Refunded"),
        ("CONTRACT_COMPLETED", "Contract Completed"),
        ("DISPUTE_OPENED", "Dispute Opened"),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activities"
    )

    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_TYPES
    )

    description = models.TextField()

    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["activity_type", "created_at"]),
        ]

    def __str__(self):
        return f"{self.activity_type} @ {self.created_at}"
