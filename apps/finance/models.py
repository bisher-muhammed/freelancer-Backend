from django.db import models

from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

class LedgerEntry(models.Model):
    ENTRY_TYPE = [
        ("subscription", "Subscription Income"),
        ("commission", "Commission Income"),
        ("escrow_deposit", "Client Escrow Deposit"),
        ("escrow_release", "Escrow Release"),
        ("payout", "Freelancer Payout"),
        ("refund", "Refund"),
    ]

    entry_type = models.CharField(max_length=30, choices=ENTRY_TYPE)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="External or internal reference (subscription, escrow, payout, etc.)"
    )

    # Context (optional but powerful)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    contract = models.ForeignKey(
        "contract.Contract", null=True, blank=True, on_delete=models.SET_NULL
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

