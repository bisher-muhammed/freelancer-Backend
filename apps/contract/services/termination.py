import logging
from decimal import Decimal
from rest_framework.exceptions import ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import BillingUnit
from apps.applications.models import EscrowPayment
from apps.contract.models import Contract
from apps.finance.services import record_entry

logger = logging.getLogger(__name__)


def _close_open_sessions(contract):
    """
    Stop any running work session on the contract and bill it while the
    contract is still active. Ending the contract first would leave that
    tracked time unbillable (billing only runs for active contracts).
    """
    from apps.billing.services import create_billing_unit_for_session
    from apps.tracking.models import WorkSession
    from apps.tracking.services.timeblock_flagger import evaluate_timeblock_flag

    sessions = WorkSession.objects.select_for_update().filter(
        contract=contract, ended_at__isnull=True
    )
    for session in sessions:
        block = session.time_blocks.filter(ended_at__isnull=True).first()
        if block:
            block.close(reason="STOP")
            evaluate_timeblock_flag(block)
        session.ended_at = timezone.now()
        session.paused_at = None
        session.save(update_fields=["ended_at", "paused_at"])
        try:
            create_billing_unit_for_session(session)
        except DjangoValidationError:
            # Budget exhausted / escrow issue: the session is still closed
            logger.warning("Could not bill session %s while ending contract %s",
                           session.id, contract.id)


@transaction.atomic
def terminate_contract(contract, *, actor):
    if contract.status != "active":
        raise ValidationError("Only active contracts can be terminated")

    _close_open_sessions(contract)

    # Use the model method — keeps logic in one place
    contract.terminate()  # sets status, end_reason, ended_at, saves


    project = contract.offer.proposal.project
    project.status = "completed"
    project.save(update_fields=["status"])


@transaction.atomic
def complete_contract(*, contract, actor):
    """Client ends an active contract normally (work delivered)."""
    from apps.contract.models import TerminationRequest
    from apps.notifications.services.create_notifications import notify_user

    contract = Contract.objects.select_for_update().get(pk=contract.pk)

    if contract.status != "active":
        raise ValidationError("Only active contracts can be completed.")

    if TerminationRequest.objects.filter(contract=contract, status="pending").exists():
        raise ValidationError(
            "A termination request is pending for this contract. "
            "Wait for the admin decision before completing it."
        )

    _close_open_sessions(contract)

    contract.mark_completed()

    project = contract.offer.proposal.project
    project.status = "completed"
    project.save(update_fields=["status"])

    notify_user(
        recipient=contract.get_freelancer_user(),
        notif_type="SYSTEM",
        title="Contract Completed",
        message=f"The client marked '{project.title}' as completed.",
        data={"contract_id": contract.id},
    )

    return contract


@transaction.atomic
def settle_contract(*, contract, actor):
    """
    Close the escrow of an ended contract.

    - released_amount = work approved for the freelancer
      (approved / locked / paid billing units)
    - refundable_amount = the rest of the escrow, owed back to the client

    Approved units stay "approved": they are paid through the normal payout
    flow, which is the single place that books the platform fee and the
    freelancer payout in the ledger. (Marking them paid here used to mean
    the freelancer was never actually paid for them.)
    """

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

    # Unreviewed time must be decided first: once the remainder is refunded,
    # approving a pending unit later would pay out money the client got back.
    pending = BillingUnit.objects.filter(contract=contract, status="pending").count()
    if pending:
        raise ValidationError(
            f"{pending} billing unit(s) are still pending review. "
            f"Approve or reject them before settling."
        )

    # approved = reviewed and accepted
    # locked   = included in payout batch
    # paid     = already paid out
    # all three are freelancer-earned money
    earned = (
        BillingUnit.objects.select_for_update().filter(
            contract=contract,
            status__in=["approved", "locked", "paid"]
        ).aggregate(
            total=Sum("gross_amount")
        )["total"] or Decimal("0.00")
    )

    if earned > escrow.amount:
        raise ValidationError(
            f"Earned amount ({earned}) exceeds escrow ({escrow.amount})."
        )

    refundable = escrow.amount - earned

    # ── Ledger Entries ───────────────────────────

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

    return escrow
