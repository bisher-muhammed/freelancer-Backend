import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.adminpanel.models import SubscriptionPlan
from apps.finance.services import record_entry
from apps.applications.models import EscrowPayment, Offer
from apps.applications.services.create_contract import create_contract_for_offer 
from apps.notifications.services import create_notifications
from apps.notifications.services.activity import log_activity
from apps.tracking.models import ActivityLog
from apps.users.models import UserSubscription, User

logger = logging.getLogger(__name__)


class StripeEscrowProcessor:
    @transaction.atomic
    def process(self, *, offer_id, payment_intent_id, amount_total=None):
        offer = (
            Offer.objects
            .select_for_update()
            .get(id=offer_id)
        )

        # 🔒 Idempotency: one escrow per offer, whatever its current status
        # (a settled/refunded escrow must not trigger a second insert)
        if EscrowPayment.objects.filter(offer=offer).exists():
            return

        # 🔒 The escrow is booked at offer.total_budget, so the amount Stripe
        # actually charged must match it exactly (in the smallest unit).
        if amount_total is not None:
            expected = int(
                (offer.total_budget * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
            if int(amount_total) != expected:
                logger.error(
                    "Escrow amount mismatch for offer %s: charged %s, expected %s",
                    offer.id, amount_total, expected,
                )
                return

        # 🔒 Idempotency: payment intent reused
        if EscrowPayment.objects.filter(
            stripe_payment_intent_id=payment_intent_id
        ).exists():
            return

        escrow = EscrowPayment.objects.create(
            offer=offer,
            amount=offer.total_budget,
            status="funded",
            stripe_payment_intent_id=payment_intent_id,
            funded_at=timezone.now(),
        )

        # 📌 Escrow funded activity (belongs HERE)
        log_activity(
            actor=offer.client,
            activity_type="ESCROW_FUNDED",
            description="Escrow funded successfully",
            metadata={
                "offer_id": offer.id,
                "project_id": offer.proposal.project.id,
                "amount": str(escrow.amount),
            },
        )

        
        contract = create_contract_for_offer(offer)

        if not contract:
            return

        record_entry(
            entry_type="escrow_deposit",
            amount=escrow.amount,
            user=offer.client,
            reference_id=str(escrow.id),
            contract=contract,
        )

        freelancer = offer.proposal.freelancer
        client = offer.client
        project = offer.proposal.project

        create_notifications.notify_user(
            recipient=freelancer,
            notif_type="ESCROW_FUNDED",
            title="Escrow Funded 💰",
            message=f"Client funded escrow for '{project.title}'.",
            data={
                "offer_id": offer.id,
                "contract_id": contract.id,
            },
        )

        create_notifications.notify_user(
            recipient=client,
            notif_type="CONTRACT_STARTED",
            title="Contract Started ✅",
            message=f"You successfully hired {freelancer.username}.",
            data={"contract_id": contract.id},
        )




class StripeSubscriptionProcessor:

    @transaction.atomic
    def process(self, *, user_id, plan_id, stripe_session_id, amount_total=None):

        # Prevent duplicate webhook processing
        if UserSubscription.objects.filter(
            stripe_session_id=stripe_session_id
        ).exists():
            return

        user = User.objects.select_for_update().get(id=user_id)

        plan = SubscriptionPlan.objects.get(id=plan_id)

        # Check if user already has active subscription
        active_subscription_exists = user.subscriptions.filter(
            status="active",
            end_date__gt=timezone.now(),
            remaining_projects__gt=0
        ).exists()

        # Create new subscription
        subscription = UserSubscription.objects.create(
            user=user,
            plan=plan,
            stripe_session_id=stripe_session_id,
            status="queued",
        )

        # Activate immediately if no active subscription exists
        if not active_subscription_exists:
            subscription.activate()

        # Book what Stripe actually charged (the plan price may have been
        # edited between checkout and this webhook)
        charged = (
            (Decimal(int(amount_total)) / 100).quantize(Decimal("0.01"))
            if amount_total is not None
            else plan.price
        )
        if charged > 0:
            record_entry(
                entry_type="subscription",
                amount=charged,
                user=user,
                reference_id=str(subscription.id),
            )

        create_notifications.notify_user(
            recipient=user,
            notif_type="SUBSCRIPTION_ACTIVE",
            title="Plan Purchased ✅",
            message=(
                "Your subscription was activated."
                if subscription.status == "active"
                else "Your subscription was added to queue."
            ),
            data={
                "subscription_id": subscription.id
            },
        )
