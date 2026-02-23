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

    contract.status = "ended"
    contract.end_reason = "terminated"
    contract.ended_at = timezone.now()

    contract.save(
        update_fields=["status", "end_reason", "ended_at"]
    )

@transaction.atomic
def settle_contract(*, contract, actor):
    # 🔒 Hard locks
    contract = (
        Contract.objects
        .select_for_update()
        .select_related("offer")
        .get(pk=contract.pk)
    )

    if contract.status != "ended":
        raise ValidationError("Contract must be ended")

    escrow = (
        EscrowPayment.objects
        .select_for_update()
        .get(offer=contract.offer, status="funded")
    )

    # ✅ Decide billing policy EXPLICITLY
    units = BillingUnit.objects.select_for_update().filter(
        contract=contract,
        status="approved"   
    )

    earned = (
        units.aggregate(total=Sum("gross_amount"))["total"]
        or Decimal("0.00")
    )

    if earned > escrow.amount:
        raise ValidationError("Earned exceeds escrow")

    platform_fee = (
        earned * contract.platform_fee_percentage / Decimal("100")
    ).quantize(Decimal("0.01"))

    freelancer_net = earned - platform_fee
    refundable = escrow.amount - earned


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

    escrow.released_amount = earned
    escrow.refunded_amount = refundable
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

    units.update(status="paid")

    return escrow
