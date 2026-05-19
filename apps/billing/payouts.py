from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import request

from apps.applications.models import EscrowPayment
from apps.contract.models import Contract

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

        # ── Lock Escrow ───────────────────────────────────────
        escrow = (
            EscrowPayment.objects
            .select_for_update()
            .select_related("offer", "offer__client")
            .get(id=escrow_id)
        )

        # ── Lock Contract ─────────────────────────────────────
        contract = (
            Contract.objects
            .select_for_update()
            .get(offer=escrow.offer)
        )

        # ── Validations ───────────────────────────────────────

        if contract.status != "ended":
            raise ValidationError(
                f"Contract is not ended "
                f"(current status: '{contract.status}')."
            )

        if contract.end_reason != "terminated":
            raise ValidationError(
                "Refund flow is only for terminated contracts."
            )

        if escrow.status == "refunded":
            raise ValidationError(
                "Refund already completed."
            )

        if escrow.status == "refund_processing":
            raise ValidationError(
                "Refund already in progress."
            )

        if escrow.status != "settled":
            raise ValidationError(
                f"Escrow must be settled before refunding "
                f"(current status: '{escrow.status}')."
            )

        # IMPORTANT:
        # refundable_amount = amount eligible for refund
        refund_amount = escrow.refundable_amount

        if refund_amount <= 0:
            raise ValidationError(
                "Nothing to refund."
            )

        # ── Mark Processing ───────────────────────────────────

        escrow.status = "refund_processing"

        escrow.save(
            update_fields=["status"]
        )

        # ── Stripe Refund ─────────────────────────────────────

        try:

            # stripe.Refund.create(
            #     payment_intent=escrow.stripe_payment_intent_id,
            #     amount=int(refund_amount * 100),
            # )

            pass

        except Exception as e:

            escrow.status = "settled"

            escrow.save(
                update_fields=["status"]
            )

            raise ValidationError(
                f"Refund failed: {str(e)}"
            )

        # ── Ledger Entry ──────────────────────────────────────

        record_entry(
            entry_type="client_refund_executed",
            amount=refund_amount,
            user=escrow.offer.client,
            reference_id=str(escrow.id),
        )

        # ── Finalize ──────────────────────────────────────────

        # actual refunded money
        escrow.refunded_amount = refund_amount

        # nothing left pending refund
        escrow.refundable_amount = Decimal("0.00")

        escrow.status = "refunded"

        escrow.refunded_at = timezone.now()

        escrow.refunded_by = actor

        escrow.save(
            update_fields=[
                "refunded_amount",
                "refundable_amount",
                "status",
                "refunded_at",
                "refunded_by",
            ]
        )

        return escrow




