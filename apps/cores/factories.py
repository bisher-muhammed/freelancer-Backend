"""Small object builders shared by the app test suites."""
from datetime import timedelta
from decimal import Decimal
from itertools import count

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.applications.models import EscrowPayment, Offer, Proposal
from apps.applications.services.create_contract import create_contract_for_offer
from apps.freelancer.models import FreelancerProfile
from apps.users.models import Project

User = get_user_model()
_seq = count(1)

PASSWORD = "Str0ng!Passw0rd"


def make_user(role="client", **kwargs):
    n = next(_seq)
    kwargs.setdefault("email", f"{role}{n}@example.com")
    kwargs.setdefault("username", f"{role}{n}")
    user = User.objects.create_user(password=PASSWORD, role=role, **kwargs)
    return user


def make_admin(**kwargs):
    return make_user(role="admin", is_staff=True, is_superuser=True, **kwargs)


def make_freelancer(**profile_kwargs):
    user = make_user(role="freelancer")
    profile_kwargs.setdefault("title", "Developer")
    profile_kwargs.setdefault("bio", "Experienced developer")
    FreelancerProfile.objects.create(user=user, **profile_kwargs)
    return user


def make_project(client, **kwargs):
    kwargs.setdefault("title", "Build a website")
    kwargs.setdefault("description", "A sufficiently long project description.")
    kwargs.setdefault("budget_type", "hourly")
    kwargs.setdefault("hourly_min_rate", Decimal("10.00"))
    kwargs.setdefault("hourly_max_rate", Decimal("50.00"))
    kwargs.setdefault("experience_level", "entry")
    kwargs.setdefault("duration", "1 month")
    return Project.objects.create(client=client, **kwargs)


def make_proposal(project, freelancer, **kwargs):
    kwargs.setdefault("cover_letter", "x" * 120)
    if project.budget_type == "hourly":
        kwargs.setdefault("bid_hourly_rate", Decimal("20.00"))
    else:
        kwargs.setdefault("bid_fixed_price", Decimal("100.00"))
    return Proposal.objects.create(project=project, freelancer=freelancer, **kwargs)


def make_offer(proposal, *, total_budget="100.00", rate="10.00", status="accepted", **kwargs):
    kwargs.setdefault("valid_until", timezone.now() + timedelta(days=7))
    return Offer.objects.create(
        proposal=proposal,
        client=proposal.project.client,
        freelancer=proposal.freelancer.freelancer_profile,
        total_budget=Decimal(total_budget),
        agreed_hourly_rate=Decimal(rate),
        status=status,
        **kwargs,
    )


def make_active_contract(*, total_budget="100.00", rate="10.00"):
    """Client + freelancer with a funded escrow and an active contract."""
    client = make_user("client")
    freelancer = make_freelancer()
    project = make_project(client)
    proposal = make_proposal(project, freelancer, status="accepted")
    offer = make_offer(proposal, total_budget=total_budget, rate=rate)
    EscrowPayment.objects.create(
        offer=offer,
        amount=offer.total_budget,
        status="funded",
        stripe_payment_intent_id=f"pi_test_{offer.id}",
        funded_at=timezone.now(),
    )
    contract = create_contract_for_offer(offer)
    return contract
