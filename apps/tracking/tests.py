from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.billing.models import BillingUnit
from apps.cores.factories import make_active_contract, make_admin, make_freelancer
from apps.tracking.models import TimeBlock, TimeBlockExplanation, WorkSession


class TrackingSessionTests(TestCase):
    def setUp(self):
        self.contract = make_active_contract(total_budget="100.00", rate="10.00")
        self.freelancer = self.contract.get_freelancer_user()
        self.api = APIClient()
        self.api.force_authenticate(self.freelancer)

    def _start(self, contract_id=None):
        return self.api.post(
            "/api/tracker/session/start/",
            {"contract_id": contract_id or self.contract.id, "device_id": "dev-1"},
            format="json",
        )

    def _backdate_open_block(self, session_id, seconds):
        TimeBlock.objects.filter(session_id=session_id, ended_at__isnull=True).update(
            started_at=timezone.now() - timedelta(seconds=seconds)
        )

    def test_start_stop_creates_billing_unit(self):
        res = self._start()
        self.assertEqual(res.status_code, 201, res.data)
        session_id = res.data["session_id"]
        self._backdate_open_block(session_id, 3600)

        res = self.api.post(f"/api/tracker/session/{session_id}/stop/", {}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        unit = BillingUnit.objects.get(session_id=session_id)
        self.assertEqual(unit.gross_amount, Decimal("10.00"))  # 1h x 10/h
        self.assertEqual(unit.status, "pending")

    def test_cannot_start_session_on_someone_elses_contract(self):
        other = make_active_contract()
        res = self._start(contract_id=other.id)
        self.assertEqual(res.status_code, 400)
        self.assertFalse(WorkSession.objects.exists())

    def test_client_cannot_start_session(self):
        self.api.force_authenticate(self.contract.get_client())
        res = self._start()
        self.assertEqual(res.status_code, 400)

    def test_other_user_cannot_stop_or_pause_my_session(self):
        session_id = self._start().data["session_id"]
        intruder = make_freelancer()
        self.api.force_authenticate(intruder)
        for action in ("stop", "pause", "idle-flush"):
            res = self.api.post(
                f"/api/tracker/session/{session_id}/{action}/", {"idle_seconds": 5}, format="json"
            )
            self.assertEqual(res.status_code, 404, action)
        self.assertIsNone(WorkSession.objects.get(id=session_id).ended_at)

    def test_stop_succeeds_even_when_budget_is_exhausted(self):
        # Exhaust the escrow with an existing pending unit
        first = self._start().data["session_id"]
        self._backdate_open_block(first, 36000)  # 10h x 10 = 100 = whole budget
        self.api.post(f"/api/tracker/session/{first}/stop/", {}, format="json")

        second = self._start().data["session_id"]
        self._backdate_open_block(second, 600)
        res = self.api.post(f"/api/tracker/session/{second}/stop/", {}, format="json")

        # Previously the billing ValidationError rolled back the stop (500)
        # and left the session open forever.
        self.assertEqual(res.status_code, 200)
        self.assertIn("budget exhausted", res.data["billing_error"])
        self.assertIsNotNone(WorkSession.objects.get(id=second).ended_at)
        self.assertFalse(BillingUnit.objects.filter(session_id=second).exists())

    def test_pending_units_count_against_escrow_cap(self):
        first = self._start().data["session_id"]
        self._backdate_open_block(first, 6 * 3600)  # 60.00
        self.api.post(f"/api/tracker/session/{first}/stop/", {}, format="json")

        second = self._start().data["session_id"]
        self._backdate_open_block(second, 6 * 3600)  # would be 60.00
        self.api.post(f"/api/tracker/session/{second}/stop/", {}, format="json")

        units = BillingUnit.objects.filter(contract=self.contract)
        total = sum(u.gross_amount for u in units)
        self.assertEqual(total, Decimal("100.00"))
        capped = units.get(session_id=second)
        self.assertEqual(capped.gross_amount, Decimal("40.00"))
        self.assertEqual(capped.billable_seconds, 4 * 3600)

    def test_device_check_requires_device_id(self):
        res = self.api.post("/api/tracker/device/check-or-create/", {}, format="json")
        self.assertEqual(res.status_code, 400)


class TimeBlockExplanationListTests(TestCase):
    def setUp(self):
        contract = make_active_contract()
        self.freelancer = contract.get_freelancer_user()
        session = WorkSession.objects.create(user=self.freelancer, contract=contract, device_id="d")
        block = TimeBlock.objects.create(session=session, ended_at=timezone.now(), is_flagged=True)
        TimeBlockExplanation.objects.create(block=block, freelancer=self.freelancer, explanation="Meeting")
        self.api = APIClient()

    def test_freelancer_lists_own_explanations(self):
        self.api.force_authenticate(self.freelancer)
        res = self.api.get("/api/time-blocks/explain/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)

    def test_admin_can_filter_flagged(self):
        self.api.force_authenticate(make_admin())
        res = self.api.get("/api/time-blocks/explain/?flagged=true")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 1)
