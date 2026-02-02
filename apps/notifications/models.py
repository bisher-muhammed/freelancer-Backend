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

    # Optional metadata (store IDs like project_id, contract_id)
    data = models.JSONField(default=dict, blank=True)

    # Status flags
    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification({self.recipient.username}, {self.notif_type})"
