from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import PayoutBatch


class PayoutProcessor:
    def process(self, payout: PayoutBatch):
        raise NotImplementedError


class MockPayoutProcessor(PayoutProcessor):
    """
    Simulated payout processor.
    Used for portfolio / non-commercial environments.
    """

    def process(self, payout: PayoutBatch):
        if payout.status != "pending":
            raise ValidationError(
                f"Payout {payout.id} cannot be processed from status '{payout.status}'."
            )

        with transaction.atomic():
            payout.status = "paid"
            payout.paid_at = timezone.now()
            payout.save(update_fields=["status", "paid_at"])

            for unit in payout.billing_units.select_for_update():
                unit.mark_paid()
