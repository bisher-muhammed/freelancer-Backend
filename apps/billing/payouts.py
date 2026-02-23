from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import request

from apps.applications.models import EscrowPayment

from .models import PayoutBatch

from apps.finance.services import record_entry
from apps.notifications.services.activity import log_activity
from apps.notifications.services import create_notifications


class PayoutProcessor:
    def process(self, payout: PayoutBatch):
        raise NotImplementedError


class MockPayoutProcessor(PayoutProcessor):
    def process(self, payout: PayoutBatch):
        
        if payout.status != "pending":
            raise ValidationError(
                f"Payout {payout.id} cannot be processed from status '{payout.status}'."
            )

        with transaction.atomic():
            
            payout = (
                PayoutBatch.objects
                .select_for_update()
                .get(id=payout.id)
            )

            if payout.status == "paid":
                return  # idempotent exit

            
            payout.status = "paid"
            payout.paid_at = timezone.now()
            payout.save(update_fields=["status", "paid_at"])

            # 2️⃣ Mark billing units paid
            for unit in payout.billing_units.select_for_update():
                unit.mark_paid()

            
            record_entry(
                entry_type="freelancer_payout",
                amount=payout.total_net,
                user=payout.freelancer.user,
                reference_id=str(payout.id),
            )

            
            if payout.platform_fee > 0:
                record_entry(
                    entry_type="platform_fee",
                    amount=payout.platform_fee,
                    user=None,  # system/platform
                    reference_id=str(payout.id),
                )

            
            log_activity(
                activity_type="PAYMENT_PROCESSED",
                actor=payout.freelancer.user,
                description=(
                    f"Payout of ₹{payout.total_net} released to "
                    f"{payout.freelancer.user.username}"
                ),
                metadata={
                    "payout_id": payout.id,
                    "freelancer_id": payout.freelancer.id,
                    "platform_fee": str(payout.platform_fee),
                },
            )

            
            create_notifications.notify_user(
                recipient=payout.freelancer.user,
                notif_type="PAYMENT_COMPLETED",
                title="Payout Released 💸",
                message=f"₹{payout.total_net} has been transferred to your account.",
                data={"payout_id": payout.id},
            )



class EscrowRefundProcessor:
    @transaction.atomic
    def process(self, *, escrow_id: int, actor):
        escrow = (
            EscrowPayment.objects
            .select_for_update()   # 🔒 THIS IS THE KEY
            .select_related("offer__client", "contract")
            .get(id=escrow_id)
        )

        contract = escrow.contract

        if contract.status != "terminated":
            raise ValidationError("Contract not terminated")

        if escrow.status == "refunded":
            raise ValidationError("Refund already completed")

        if escrow.status == "refund_processing":
            raise ValidationError("Refund already in progress")

        if escrow.status != "settled":
            raise ValidationError("Escrow not refundable")

        refundable_amount = escrow.refunded_amount  # or computed

        if refundable_amount <= 0:
            raise ValidationError("Nothing to refund")

        # 🔒 LOCK THE ACTION
        escrow.status = "refund_processing"
        escrow.save(update_fields=["status"])

        # ---- Stripe refund would go here ----
        # stripe.Refund.create(...)

        record_entry(
            entry_type="client_refund_executed",
            amount=refundable_amount,
            user=escrow.offer.client,
            reference_id=str(escrow.id),
        )

        escrow.status = "refunded"
        escrow.refunded_at = timezone.now()
        escrow.refunded_by = request.user
        escrow.save(
            update_fields=["status", "refunded_at", "refunded_by"]
        )
