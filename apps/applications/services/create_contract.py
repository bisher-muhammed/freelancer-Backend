from apps.contract.models import Contract


def create_contract_for_offer(offer):
    """
    Create contract only after:
    - offer accepted
    - escrow payment completed
    """

    # Prevent duplicates
    if hasattr(offer, "contract"):
        return offer.contract

    # Offer must be accepted
    if offer.status != "accepted":
        return None  # Don't crash webhook

    # Escrow must exist
    if not hasattr(offer, "payment"):
        return None

    payment = offer.payment

    # Escrow must be successful
    if payment.status != "escrowed":
        return None

    # ✅ Create contract
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
    return contract

