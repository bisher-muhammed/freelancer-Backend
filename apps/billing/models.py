import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class PayoutBatch(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("paid", "Paid"),
        ("failed", "Failed"),
    )

    freelancer = models.ForeignKey(
        "freelancer.FreelancerProfile",
        on_delete=models.CASCADE,
        related_name="payout_batches",
    )

    total_gross = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2)
    total_net = models.DecimalField(max_digits=12, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def mark_paid(self):
        self.status = "paid"
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at"])

    def __str__(self):
        return f"PayoutBatch #{self.id} → {self.freelancer.user.email}"



class BillingUnit(models.Model):
    STATUS_CHOICES = (
        ("pending", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("locked", "Locked in payout"),
        ("paid", "Paid"),
    )

    contract = models.ForeignKey(
        "contract.Contract",
        on_delete=models.PROTECT,
        related_name="billing_units",
    )

    freelancer = models.ForeignKey(
        "freelancer.FreelancerProfile",
        on_delete=models.PROTECT,
        related_name="billing_units",
    )

    session = models.OneToOneField(
        "tracking.WorkSession",
        on_delete=models.PROTECT,
        related_name="billing_unit",
    )

    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    billable_seconds = models.PositiveIntegerField()
    idle_seconds = models.PositiveIntegerField()

    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    gross_amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    payout_batch = models.ForeignKey(
        PayoutBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="billing_units",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def productive_seconds(self):
        return self.billable_seconds - self.idle_seconds

    def lock_for_payout(self, batch: PayoutBatch):
        if self.status != "approved":
            raise ValidationError("Only approved billing units can be paid.")
        self.status = "locked"
        self.payout_batch = batch
        self.save(update_fields=["status", "payout_batch"])

    def mark_paid(self):
        self.status = "paid"
        self.save(update_fields=["status"])

    def __str__(self):
        return f"BillingUnit #{self.id} → Freelancer {self.freelancer_id}"




class Invoice(models.Model):
    STATUS_CHOICES = (
        ("issued", "Issued"),
        ("void", "Void"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    invoice_number = models.CharField(
        max_length=32,
        unique=True,
        editable=False,
    )

    freelancer = models.ForeignKey(
        "freelancer.FreelancerProfile",
        on_delete=models.PROTECT,
        related_name="invoices",
    )

    payout_batch = models.OneToOneField(
        "billing.PayoutBatch",
        on_delete=models.PROTECT,
        related_name="invoice",
    )

    total_gross = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2)
    total_net = models.DecimalField(max_digits=12, decimal_places=2)

    currency = models.CharField(max_length=10, default="INR")

    issued_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="issued",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issued_at"]

    def __str__(self):
        return f"Invoice {self.invoice_number} - Freelancer {self.freelancer_id}"