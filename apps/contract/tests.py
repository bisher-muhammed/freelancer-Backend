from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.test import APIClient

from apps.billing.models import BillingUnit
from apps.contract.models import ContractReview, TerminationRequest
from apps.contract.services.termination import settle_contract, terminate_contract
from apps.cores.factories import make_active_contract, make_admin, make_user
from apps.finance.models import LedgerEntry
from apps.tracking.models import TimeBlock, WorkSession


def make_unit(contract, gross, status):
    session = WorkSession.objects.create(
        user=contract.get_freelancer_user(), contract=contract, device_id="d",
        ended_at=timezone.now(),
    )
    return BillingUnit.objects.create(
        contract=contract, freelancer=contract.offer.freelancer, session=session,
        period_start=session.started_at, period_end=session.ended_at,
        billable_seconds=3600, idle_seconds=0,
        hourly_rate=contract.offer.agreed_hourly_rate,
        gross_amount=Decimal(gross), status=status,
    )


class ContractAccessTests(TestCase):
    def setUp(self):
        self.contract = make_active_contract()
        self.client_user = self.contract.get_client()
        self.api = APIClient()

    def test_contract_detail_includes_freelancer_name(self):
        self.api.force_authenticate(self.client_user)
        res = self.api.get(f"/api/contracts/{self.contract.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["freelancer_name"], self.contract.get_freelancer_user().username)
        self.assertIsNone(res.data["termination_request"])
        self.assertFalse(res.data["has_review"])

        TerminationRequest.objects.create(contract=self.contract, requested_by=self.client_user)
        res = self.api.get(f"/api/contracts/{self.contract.id}/")
        self.assertEqual(res.data["termination_request"]["status"], "pending")

    def test_other_client_cannot_request_termination(self):
        self.api.force_authenticate(make_user("client"))
        res = self.api.post(f"/api/contracts/{self.contract.id}/terminate/", {"reason": "x"})
        self.assertEqual(res.status_code, 404)
        self.assertFalse(TerminationRequest.objects.exists())

    def test_owner_can_request_and_admin_can_reject_then_resubmit(self):
        self.api.force_authenticate(self.client_user)
        res = self.api.post(f"/api/contracts/{self.contract.id}/terminate/", {"reason": "x"})
        self.assertEqual(res.status_code, 201)
        tr = TerminationRequest.objects.get()

        admin_api = APIClient()
        admin_api.force_authenticate(make_admin())
        res = admin_api.post(f"/api/admin/termination-requests/{tr.id}/reject/")
        self.assertEqual(res.status_code, 200)
        tr.refresh_from_db()
        self.assertEqual(tr.status, "rejected")

        res = self.api.post(f"/api/contracts/{self.contract.id}/terminate/", {"reason": "again"})
        self.assertEqual(res.status_code, 201)
        tr.refresh_from_db()
        self.assertEqual(tr.status, "pending")

    def test_outsider_cannot_create_document_folder(self):
        self.api.force_authenticate(make_user("client"))
        res = self.api.post(f"/api/contracts/{self.contract.id}/documents-folders/", {"name": "x"})
        self.assertEqual(res.status_code, 403)

    def test_client_completes_contract_and_running_session_is_billed(self):
        freelancer = self.contract.get_freelancer_user()
        session = WorkSession.objects.create(user=freelancer, contract=self.contract, device_id="d")
        TimeBlock.objects.create(session=session)
        TimeBlock.objects.filter(session=session).update(
            started_at=timezone.now() - timedelta(hours=1)
        )

        self.api.force_authenticate(self.client_user)
        res = self.api.post(f"/api/contracts/{self.contract.id}/complete/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["end_reason"], "completed")

        session.refresh_from_db()
        self.assertIsNotNone(session.ended_at)
        self.assertEqual(BillingUnit.objects.get(session=session).gross_amount, Decimal("10.00"))
        self.contract.offer.proposal.project.refresh_from_db()
        self.assertEqual(self.contract.offer.proposal.project.status, "completed")

        # Second completion is rejected
        res = self.api.post(f"/api/contracts/{self.contract.id}/complete/")
        self.assertEqual(res.status_code, 400)

    def test_only_owning_client_can_complete(self):
        for user in (make_user("client"), self.contract.get_freelancer_user()):
            self.api.force_authenticate(user)
            res = self.api.post(f"/api/contracts/{self.contract.id}/complete/")
            self.assertEqual(res.status_code, 404)

    def test_complete_blocked_by_pending_termination(self):
        TerminationRequest.objects.create(contract=self.contract, requested_by=self.client_user)
        self.api.force_authenticate(self.client_user)
        res = self.api.post(f"/api/contracts/{self.contract.id}/complete/")
        self.assertEqual(res.status_code, 400)

    def test_contract_messages_without_chat_room_is_404(self):
        self.api.force_authenticate(self.client_user)
        res = self.api.get(f"/api/contracts/{self.contract.id}/messages/")
        self.assertEqual(res.status_code, 404)


class ReviewTests(TestCase):
    def setUp(self):
        self.contract = make_active_contract()
        terminate_contract(self.contract, actor=None)
        self.api = APIClient()
        self.api.force_authenticate(self.contract.get_client())

    def test_review_updates_freelancer_rating_and_testimonials_load(self):
        res = self.api.post(
            "/api/contract-reviews/",
            {"contract": self.contract.id, "freelancer_rating": 4, "freelancer_review": "Good"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        profile = self.contract.offer.freelancer
        profile.refresh_from_db()
        self.assertEqual(profile.total_reviews, 1)
        self.assertEqual(profile.average_rating, Decimal("4.00"))

        res = APIClient().get(f"/api/freelancers/{profile.id}/testimonials/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["results"][0]["freelancer_rating"], 4)
        self.assertIn("freelancer_email", res.data["results"][0])

    def test_review_rejected_for_active_contract(self):
        contract = make_active_contract()
        self.api.force_authenticate(contract.get_client())
        res = self.api.post(
            "/api/contract-reviews/",
            {"contract": contract.id, "freelancer_rating": 5},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(ContractReview.objects.filter(contract=contract).exists())


class SettlementTests(TestCase):
    def test_settlement_amounts_and_approved_units_stay_payable(self):
        contract = make_active_contract(total_budget="100.00", rate="10.00")
        make_unit(contract, "30.00", "paid")      # already paid out via payout batch
        approved = make_unit(contract, "20.00", "approved")  # earned, not yet paid
        make_unit(contract, "15.00", "rejected")  # not earned -> refunded
        terminate_contract(contract, actor=None)

        escrow = settle_contract(contract=contract, actor=None)

        self.assertEqual(escrow.status, "settled")
        self.assertEqual(escrow.released_amount, Decimal("50.00"))
        self.assertEqual(escrow.refundable_amount, Decimal("50.00"))

        entries = {
            e.entry_type: e.amount
            for e in LedgerEntry.objects.filter(contract=contract)
            if e.entry_type != "escrow_deposit"
        }
        # Fees/payouts are booked only by the payout flow, never here
        self.assertEqual(entries, {"client_refund_pending": Decimal("50.00")})

        # The approved unit is still waiting for a real payout
        approved.refresh_from_db()
        self.assertEqual(approved.status, "approved")

        admin_api = APIClient()
        admin_api.force_authenticate(make_admin())
        res = admin_api.post(
            "/api/admin/payouts/confirm/",
            {"freelancer_id": contract.offer.freelancer.id},
            format="json",
        )
        self.assertEqual(res.status_code, 201)
        self.assertEqual(Decimal(str(res.data["total_net"])), Decimal("18.00"))
        fee_total = sum(
            e.amount for e in LedgerEntry.objects.filter(entry_type="platform_fee")
        )
        self.assertEqual(fee_total, Decimal("2.00"))

    def test_settlement_blocked_while_units_pending(self):
        contract = make_active_contract()
        make_unit(contract, "10.00", "pending")
        terminate_contract(contract, actor=None)
        with self.assertRaises(DRFValidationError):
            settle_contract(contract=contract, actor=None)

    def test_reviews_are_frozen_after_settlement(self):
        contract = make_active_contract()
        unit = make_unit(contract, "10.00", "approved")
        terminate_contract(contract, actor=None)
        settle_contract(contract=contract, actor=None)
        api = APIClient()
        api.force_authenticate(make_admin())
        res = api.patch(
            f"/api/admin/billing-units/{unit.id}/explanation/review/", {"action": "reject"}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_refund_works_for_completed_contract(self):
        contract = make_active_contract(total_budget="100.00")
        make_unit(contract, "40.00", "approved")
        api = APIClient()
        api.force_authenticate(contract.get_client())
        self.assertEqual(api.post(f"/api/contracts/{contract.id}/complete/").status_code, 200)

        admin_api = APIClient()
        admin_api.force_authenticate(make_admin())
        listed = admin_api.get("/api/admin/contracts/completed/").data
        self.assertEqual([c["id"] for c in listed], [contract.id])
        self.assertEqual(listed[0]["offer"]["payment"]["status"], "funded")

        res = admin_api.post(f"/api/admin/contracts/{contract.id}/settle/")
        self.assertEqual(res.status_code, 200, res.data)
        with self.settings(STRIPE_REFUNDS_ENABLED=False):
            res = admin_api.post(f"/api/admin/contracts/{contract.id}/refund-escrow/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data["refunded_amount"]), Decimal("60.00"))
        # Fully handled -> no longer listed
        self.assertEqual(admin_api.get("/api/admin/contracts/completed/").data, [])

    @mock.patch("apps.billing.payouts.stripe.Refund.create")
    def test_stripe_refund_called_only_when_enabled(self, refund_create):
        contract = make_active_contract(total_budget="100.00")
        terminate_contract(contract, actor=None)
        settle_contract(contract=contract, actor=None)
        admin_api = APIClient()
        admin_api.force_authenticate(make_admin())
        with self.settings(STRIPE_REFUNDS_ENABLED=True):
            res = admin_api.post(f"/api/admin/contracts/{contract.id}/refund-escrow/")
        self.assertEqual(res.status_code, 200, res.data)
        refund_create.assert_called_once()
        kwargs = refund_create.call_args.kwargs
        self.assertEqual(kwargs["amount"], 10000)
        self.assertEqual(kwargs["payment_intent"], contract.offer.payment.stripe_payment_intent_id)

    def test_settle_requires_ended_contract(self):
        contract = make_active_contract()
        api = APIClient()
        api.force_authenticate(make_admin())
        res = api.post(f"/api/admin/contracts/{contract.id}/settle/")
        self.assertEqual(res.status_code, 400)
