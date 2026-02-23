from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.adminpanel.models import TrackingPolicy
from apps.contract.constants import contract_document_upload_path

User = settings.AUTH_USER_MODEL

class Contract(models.Model):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("ended", "Ended"),
        ("disputed", "Disputed"),
    )

    END_REASON_CHOICES = (
        ("completed", "Completed Normally"),
        ("terminated", "Terminated Early"),
    )


    # One contract per accepted offer
    offer = models.OneToOneField(
        "applications.Offer",
        on_delete=models.PROTECT,
        related_name="contract"
    )

    # Only store extra info not in the offer
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.0,
        help_text="Platform fee at the time of contract creation"
    )

    scope_summary = models.TextField(
        help_text="Short description of agreed scope / deliverables"
    )

    termination_notice_days = models.PositiveIntegerField(default=0)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active"
    )

    end_reason = models.CharField(
        max_length=20,
        choices=END_REASON_CHOICES,
        null=True,
        blank=True
    )

    tracking_required = models.BooleanField(default=False)
    tracking_policy = models.ForeignKey(
        TrackingPolicy,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )


    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    terminated_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["offer"]),
        ]

    def __str__(self):
        return f"Contract #{self.id} | Offer #{self.offer.id} | Freelancer {self.offer.freelancer}"

    def is_active(self):
        return self.status == "active"

    def mark_completed(self):
        self.status = "ended"
        self.end_reason = "completed"
        self.completed_at = timezone.now()  
        self.ended_at = timezone.now()
        self.save(update_fields=["status", "end_reason", "completed_at", "ended_at"])


    def terminate(self):
        self.status = "ended"
        self.end_reason = "terminated"
        self.ended_at = timezone.now()
        self.terminated_at = timezone.now()  # add this
        self.save(update_fields=["status", "end_reason", "ended_at", "terminated_at"])

    def mark_disputed(self):
        self.status = "disputed"
        self.save(update_fields=["status"]) 
    
    def calculate_platform_fee(amount, percent):
        return (amount * percent / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    def get_freelancer_user(self):
        return self.offer.freelancer.user
    
    def get_client(self):
        return self.offer.client
    







class ContractDocumentFolder(models.Model):
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="document_folders"
    )
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("contract", "name")
        indexes = [
            models.Index(fields=["contract", "name"]),
        ]

    def __str__(self):
        return f"{self.name} (Contract #{self.contract.id})"


class ContractDocument(models.Model):
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="documents"
    )
    folder = models.ForeignKey(
        ContractDocumentFolder,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="documents"
    )

    file = models.FileField(upload_to="contract_documents/")
    original_name = models.CharField(max_length=255)

    mime_type = models.CharField(max_length=100)

    uploaded_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["contract"]),
            models.Index(fields=["folder"]),
        ]

    def __str__(self):
        return self.original_name

    @property
    def file_size(self):
        return self.file.size if self.file else 0

    @property
    def extension(self):
        return self.original_name.split(".")[-1].lower()

    



class TerminationRequest(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="termination_request"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )
    reason = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_terminations"
    )



class ContractReview(models.Model):
    RATING_CHOICES = (
        (1, "Very Bad"),
        (2, "Bad"),
        (3, "Average"),
        (4, "Good"),
        (5, "Excellent"),
    )

    contract = models.OneToOneField(
        Contract,
        on_delete=models.CASCADE,
        related_name="review",
        help_text="Review exists only for ended contracts"
    )

    
    freelancer_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES
    )
    freelancer_review = models.TextField(blank=True)

    # Platform experience (optional, future-safe)
    platform_rating = models.PositiveSmallIntegerField(
        choices=RATING_CHOICES,
        null=True,
        blank=True
    )
    platform_feedback = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["freelancer_rating"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"Contract #{self.contract_id} – {self.freelancer_rating}/5"

    @property
    def client(self):
        return self.contract.offer.client

    @property
    def freelancer(self):
        return self.contract.offer.freelancer.freelancer_profile
