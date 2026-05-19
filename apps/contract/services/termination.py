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

    contract = (
        Contract.objects
        .select_for_update()
        .select_related("offer")
        .get(pk=contract.pk)
    )

    if contract.status != "ended":
        raise ValidationError(
            f"Contract must be ended before settlement "
            f"(current status: '{contract.status}')."
        )

    try:
        escrow = (
            EscrowPayment.objects
            .select_for_update()
            .get(offer=contract.offer, status="funded")
        )

    except EscrowPayment.DoesNotExist:
        raise ValidationError(
            "Escrow not found or already settled."
        )

    # IMPORTANT:
    # approved = reviewed and accepted
    # locked   = included in payout batch
    # paid     = already paid out
    #
    # all three are freelancer-earned money

    earned_units = BillingUnit.objects.select_for_update().filter(
        contract=contract,
        status__in=["approved", "locked", "paid"]
    )

    earned = (
        earned_units.aggregate(
            total=Sum("gross_amount")
        )["total"] or Decimal("0.00")
    )

    if earned > escrow.amount:
        raise ValidationError(
            f"Earned amount ({earned}) exceeds escrow ({escrow.amount})."
        )

    platform_fee = (
        earned * contract.platform_fee_percentage / Decimal("100")
    ).quantize(Decimal("0.01"))

    freelancer_net = earned - platform_fee

    refundable = escrow.amount - earned

    # ── Ledger Entries ───────────────────────────

    if freelancer_net > 0:
        record_entry(
            entry_type="freelancer_net_earned",
            amount=freelancer_net,
            user=contract.get_freelancer_user(),
            contract=contract,
        )

    if platform_fee > 0:
        record_entry(
            entry_type="platform_fee",
            amount=platform_fee,
            contract=contract,
        )

    if refundable > 0:
        record_entry(
            entry_type="client_refund_pending",
            amount=refundable,
            user=contract.get_client(),
            contract=contract,
        )

    # ── Escrow Accounting ───────────────────────

    escrow.released_amount = earned

    # pending refund amount
    escrow.refundable_amount = refundable

    # actual stripe-refunded amount
    escrow.refunded_amount = Decimal("0.00")

    escrow.status = "settled"
    escrow.settled_at = timezone.now()

    escrow.save(
        update_fields=[
            "released_amount",
            "refundable_amount",
            "refunded_amount",
            "status",
            "settled_at",
        ]
    )

    # ONLY approved units become paid
    BillingUnit.objects.filter(
        contract=contract,
        status="approved"
    ).update(status="paid")

    return escrow


