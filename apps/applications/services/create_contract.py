from django.db import transaction

from apps.contract.models import Contract
from apps.applications.models import EscrowPayment
from apps.notifications.services.activity import log_activity


@transaction.atomic
def create_contract_for_offer(offer):
    """
    Idempotent contract creation.
    Called from payment webhook after escrow funding.
    """

    if hasattr(offer, "contract"):
        return offer.contract

    # ❌ Offer must already be accepted
    if offer.status != "accepted":
        return None

    # 🔒 Escrow must exist AND be funded
    escrow = (
        EscrowPayment.objects
        .select_for_update()
        .filter(
            offer=offer,
            status="funded",
        )
        .first()
    )

    if not escrow:
        return None

    contract = Contract.objects.create(
        offer=offer,
        platform_fee_percentage=10.0,
        scope_summary=f"Contract based on offer #{offer.id}",
        termination_notice_days=7,
        tracking_required=False,
        tracking_policy=None,
    )

    project = offer.proposal.project
    project.status = "in_progress"
    project.save(update_fields=["status"])

    # 📌 Contract creation activity (belongs HERE)
    log_activity(
        actor=offer.client,
        activity_type="CONTRACT_CREATED",
        description=f"Contract created for offer #{offer.id}",
        metadata={
            "offer_id": offer.id,
            "escrow_id": escrow.id,
            "contract_id": contract.id,
        },
    )

    return contract

