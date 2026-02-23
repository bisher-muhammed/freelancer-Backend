from decimal import Decimal
from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import BillingUnit
from apps.applications.models import EscrowPayment
from apps.contract.models import Contract
from apps.finance.services import record_entry


@transaction.atomic
def terminate_contract(contract, *, actor):
    if contract.status != "active":
        raise ValidationError("Only active contracts can be terminated")

    # Use the model method — keeps logic in one place
    contract.terminate()  # sets status, end_reason, ended_at, saves

    
    project = contract.offer.proposal.project
    project.status = "completed"
    project.save(update_fields=["status"])

@transaction.atomic
def settle_contract(*, contract, actor):
    """
    Settles a terminated (or completed) contract:
      1. Locks contract + escrow rows
      2. Computes earned (approved billing units), platform fee, freelancer net, refundable
      3. Writes ledger entries
      4. Marks billing units as 'paid'
      5. Marks escrow as 'settled'

    FIX: Checks status='ended' AND end_reason='terminated' (or 'completed').
         Previously checked for a non-existent status='terminated'.
    """
    # 🔒 Lock contract row
    contract = (
        Contract.objects
        .select_for_update()
        .select_related("offer")
        .get(pk=contract.pk)
    )

    # FIX: Contract.STATUS_CHOICES has 'ended', not 'terminated'.
    # Terminated contracts have status='ended' + end_reason='terminated'.
    if contract.status != "ended":
        raise ValidationError(
            f"Contract must be ended before settlement (current status: '{contract.status}')."
        )

    # 🔒 Lock escrow — must be 'funded' (not yet settled)
    try:
        escrow = (
            EscrowPayment.objects
            .select_for_update()
            .get(offer=contract.offer, status="funded")
        )
    except EscrowPayment.DoesNotExist:
        raise ValidationError(
            "Escrow not found or not in 'funded' state. "
            "It may have already been settled."
        )

    # Lock and fetch approved billing units
    # FIX: Also include 'locked' units — work submitted but pending payment
    units = BillingUnit.objects.select_for_update().filter(
        contract=contract,
        status__in=["approved", "locked"]
    )

    earned = (
        units.aggregate(total=Sum("gross_amount"))["total"]
        or Decimal("0.00")
    )

    if earned > escrow.amount:
        raise ValidationError(
            f"Earned amount (₹{earned}) exceeds escrow (₹{escrow.amount}). "
            "Manual review required."
        )

    platform_fee = (
        earned * contract.platform_fee_percentage / Decimal("100")
    ).quantize(Decimal("0.01"))

    freelancer_net = earned - platform_fee
    refundable = escrow.amount - earned

    # ── Write ledger entries ──────────────────────────────────────────────
    if freelancer_net > 0:
        record_entry(
            entry_type="freelancer_net_earned",
            amount=freelancer_net,
            user=contract.get_freelancer_user(),
            contract=contract,
            actor=actor,
        )

    if platform_fee > 0:
        record_entry(
            entry_type="platform_fee",
            amount=platform_fee,
            contract=contract,
            actor=actor,
        )

    if refundable > 0:
        record_entry(
            entry_type="client_refund_pending",
            amount=refundable,
            user=contract.get_client(),
            contract=contract,
            actor=actor,
        )

    # ── Update escrow ─────────────────────────────────────────────────────
    # FIX: refunded_amount stores the COMPUTED refundable value here.
    # The actual Stripe refund is done separately in EscrowRefundProcessor.
    escrow.released_amount = earned
    escrow.refunded_amount = refundable   # Pending refund — not yet sent to Stripe
    escrow.status = "settled"
    escrow.settled_at = timezone.now()
    escrow.save(
        update_fields=[
            "released_amount",
            "refunded_amount",
            "status",
            "settled_at",
        ]
    )

    # Mark all approved/locked billing units as paid
    units.update(status="paid")

    return escrow
