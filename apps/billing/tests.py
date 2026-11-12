from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import BillingUnit
from apps.cores.factories import make_active_contract, make_admin
from apps.tracking.models import WorkSession


def make_unit(contract, gross, status="pending"):
    session = WorkSession.objects.create(
        user=contract.get_freelancer_user(), contract=contract, device_id="d",
        ended_at=timezone.now(),
    )
    return BillingUnit.objects.create(
        contract=contract,
        freelancer=contract.offer.freelancer,
        session=session,
        period_start=session.started_at,
        period_end=session.ended_at,
        billable_seconds=3600,
        idle_seconds=0,
        hourly_rate=contract.offer.agreed_hourly_rate,
        gross_amount=Decimal(gross),
        status=status,
    )


class BillingReviewTests(TestCase):
    def setUp(self):
        self.contract = make_active_contract(total_budget="100.00", rate="10.00")
        self.api = APIClient()
        self.api.force_authenticate(make_admin())

    def _review(self, unit, action):
        return self.api.patch(
            f"/api/admin/billing-units/{unit.id}/explanation/review/", {"action": action}, format="json"
        )

    def test_approve_pending_unit(self):
        unit = make_unit(self.contract, "10.00")
        self.assertEqual(self._review(unit, "approve").status_code, 200)
        unit.refresh_from_db()
        self.assertEqual(unit.status, "approved")

    def test_paid_unit_cannot_be_re_reviewed(self):
        # Re-approving a paid unit would make it payable a second time
        unit = make_unit(self.contract, "10.00", status="paid")
        self.assertEqual(self._review(unit, "approve").status_code, 400)
        self.assertEqual(self._review(unit, "reject").status_code, 400)

    def test_approval_cannot_exceed_escrow(self):
        make_unit(self.contract, "95.00", status="approved")
        unit = make_unit(self.contract, "10.00")
        self.assertEqual(self._review(unit, "approve").status_code, 400)


class PayoutTests(TestCase):
    def setUp(self):
        self.contract = make_active_contract(total_budget="100.00", rate="10.00")
        self.api = APIClient()
        self.api.force_authenticate(make_admin())

    def test_payout_math_and_invoice(self):
        make_unit(self.contract, "33.33", status="approved")
        make_unit(self.contract, "16.67", status="approved")
        res = self.api.post(
            "/api/admin/payouts/confirm/",
            {"freelancer_id": self.contract.offer.freelancer.id},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        # 50.00 gross, 10% fee = 5.00, net 45.00
        self.assertEqual(Decimal(str(res.data["total_net"])), Decimal("45.00"))
        self.assertFalse(
            BillingUnit.objects.filter(contract=self.contract, status="approved").exists()
        )

    def test_freelancer_lists_own_billing_units(self):
        make_unit(self.contract, "10.00")
        api = APIClient()
        api.force_authenticate(self.contract.get_freelancer_user())
        res = api.get("/api/freelancer/billing-units/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)

    def test_invoice_list_and_earnings(self):
        make_unit(self.contract, "20.00", status="approved")
        self.api.post(
            "/api/admin/payouts/confirm/",
            {"freelancer_id": self.contract.offer.freelancer.id},
            format="json",
        )
        api = APIClient()
        api.force_authenticate(self.contract.get_freelancer_user())
        res = api.get("/api/invoices/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        self.assertIsInstance(res.data["results"][0]["payout_batch_id"], int)

        res = api.get("/api/freelancer/earnings/summary/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(Decimal(res.data["total_net"]), Decimal("18.00"))
