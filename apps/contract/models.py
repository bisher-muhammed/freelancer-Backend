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
        ("completed", "Completed"),
        ("terminated", "Terminated"),
        ("disputed", "Disputed"),
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
        self.status = "completed"
        self.completed_at = timezone.now()
        self.ended_at = self.completed_at
        self.save(update_fields=["status", "completed_at", "ended_at"])

    def terminate(self):
        self.status = "terminated"
        self.terminated_at = timezone.now()
        self.ended_at = self.terminated_at
        self.save(update_fields=["status", "terminated_at", "ended_at"])
    def mark_disputed(self):
        self.status = "disputed"
        self.save(update_fields=["status"]) 
    
    def calculate_platform_fee(self):
        """
        Platform fee is always calculated from total escrow upfront.
        """
        amount = self.offer.total_budget
        return (self.platform_fee_percentage / 100) * amount

    def get_freelancer_user(self):
        return self.offer.freelancer.user
    
    def get_client(self):
        return self.offer.client
    




User = get_user_model()


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

    