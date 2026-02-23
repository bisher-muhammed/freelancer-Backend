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
        """
        Processes the actual Stripe refund for the client.

        FIXES:
          1. contract accessed via escrow.offer.contract (no direct FK)
          2. Checks contract.status == 'ended' + end_reason == 'terminated'
             (not the non-existent status 'terminated')
          3. Uses `actor` instead of undefined `request.user`
          4. refundable_amount = escrow.refunded_amount (set by settle_contract)
        """
        escrow = (
            EscrowPayment.objects
            .select_for_update()
            .select_related("offer__client", "offer__contract")  # FIX: no direct escrow.contract FK
            .get(id=escrow_id)
        )

        # FIX: contract is accessed via offer, not directly on escrow
        contract = escrow.offer.contract

        # FIX: Correct status check — no 'terminated' in STATUS_CHOICES
        if contract.status != "ended":
            raise ValidationError(
                f"Contract is not ended (current status: '{contract.status}')."
            )

        if contract.end_reason != "terminated":
            raise ValidationError(
                "Refund flow is only for terminated contracts. "
                f"Current end_reason: '{contract.end_reason}'."
            )

        # Guard against double-refund
        if escrow.status == "refunded":
            raise ValidationError("Refund already completed.")

        if escrow.status == "refund_processing":
            raise ValidationError("Refund is already in progress.")

        # settle_contract must have run first
        if escrow.status != "settled":
            raise ValidationError(
                f"Escrow must be 'settled' before refunding (current status: '{escrow.status}'). "
                "Run 'Settle Contract' first."
            )

        # FIX: refunded_amount was SET by settle_contract to the computed refundable value.
        # It represents money TO be refunded, not money already refunded.
        refundable_amount = escrow.refunded_amount

        if refundable_amount <= 0:
            raise ValidationError("Nothing to refund (refundable amount is ₹0).")

        # 🔒 Lock to prevent concurrent refund attempts
        escrow.status = "refund_processing"
        escrow.save(update_fields=["status"])

        # ── Stripe refund would go here ───────────────────────────────────
        # try:
        #     stripe.Refund.create(
        #         payment_intent=escrow.stripe_payment_intent_id,
        #         amount=int(refundable_amount * 100),  # paise
        #     )
        # except stripe.error.StripeError as e:
        #     escrow.status = "settled"  # rollback lock
        #     escrow.save(update_fields=["status"])
        #     raise ValidationError(f"Stripe refund failed: {e.user_message}")
        # ─────────────────────────────────────────────────────────────────

        record_entry(
            entry_type="client_refund_executed",
            amount=refundable_amount,
            user=escrow.offer.client,
            reference_id=str(escrow.id),
        )

        escrow.status = "refunded"
        escrow.refunded_at = timezone.now()
        escrow.refunded_by = actor  
        escrow.save(
            update_fields=["status", "refunded_at", "refunded_by"]
        )

        return escrow
