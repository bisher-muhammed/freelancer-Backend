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



class StripeEscrowProcessor:
    @transaction.atomic
    def process(self, *, offer_id, payment_intent_id):
        offer = (
            Offer.objects
            .select_for_update()
            .get(id=offer_id)
        )

        # 🔒 Idempotency: escrow already funded
        if EscrowPayment.objects.filter(
            offer=offer,
            status="funded",
        ).exists():
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
    def process(self, *, user_id, plan_id):
        user = User.objects.select_for_update().get(id=user_id)
        plan = SubscriptionPlan.objects.get(id=plan_id)

        # 🔒 Idempotency: active subscription already exists
        if UserSubscription.objects.filter(
            user=user,
            end_date__gt=timezone.now(),
        ).exists():
            return

        subscription = UserSubscription.objects.create(
            user=user,
            plan=plan,
        )

        
        record_entry(
            entry_type="subscription",
            amount=plan.price,
            user=user,
            reference_id=str(subscription.id),
        )

        create_notifications.notify_user(
            recipient=user,
            notif_type="SUBSCRIPTION_ACTIVE",
            title="Plan Activated ✅",
            message="Your subscription payment was successful.",
            data={"subscription_id": subscription.id},
        )
