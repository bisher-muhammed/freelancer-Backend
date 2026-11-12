from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.applications.models import EscrowPayment
from apps.contract.models import Contract
from apps.cores.factories import (
    make_active_contract,
    make_admin,
    make_freelancer,
    make_offer,
    make_project,
    make_proposal,
    make_user,
)
from apps.notifications.services.create_notifications import notify_user
from apps.tracking.models import Screenshot, ScreenshotWindow, TimeBlock, WorkSession
from apps.users.models import ClientProfile
from apps.users.payments.processors import StripeEscrowProcessor

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01"
    b"\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def cookie_client(user=None):
    api = APIClient()
    if user is not None:
        api.cookies["access_token"] = str(AccessToken.for_user(user))
    return api


def fetch(api, url):
    res = api.get(url)
    if hasattr(res, "streaming_content"):
        b"".join(res.streaming_content)
    return res


class ProtectedMediaTests(TestCase):
    def setUp(self):
        self.contract = make_active_contract()
        self.freelancer = self.contract.get_freelancer_user()
        session = WorkSession.objects.create(user=self.freelancer, contract=self.contract, device_id="d")
        block = TimeBlock.objects.create(session=session)
        window = ScreenshotWindow.objects.create(
            block=block, start_at=timezone.now(), end_at=timezone.now() + timedelta(minutes=10)
        )
        self.shot = Screenshot.objects.create(
            block=block, window=window, taken_at_client=timezone.now(),
            image=SimpleUploadedFile("shot.png", PNG, content_type="image/png"),
        )
        self.url = f"/media/{self.shot.image.name}"

    def test_screenshot_visible_only_to_contract_parties_and_staff(self):
        self.assertEqual(fetch(cookie_client(), self.url).status_code, 404)
        self.assertEqual(fetch(cookie_client(make_user("client")), self.url).status_code, 404)
        self.assertEqual(fetch(cookie_client(self.freelancer), self.url).status_code, 200)
        self.assertEqual(fetch(cookie_client(self.contract.get_client()), self.url).status_code, 200)
        self.assertEqual(fetch(cookie_client(make_admin()), self.url).status_code, 200)

    def test_profile_pictures_stay_public(self):
        profile = ClientProfile.objects.create(
            user=self.contract.get_client(), company_name="Acme",
            profile_picture=SimpleUploadedFile("me.png", PNG, content_type="image/png"),
        )
        res = fetch(cookie_client(), f"/media/{profile.profile_picture.name}")
        self.assertEqual(res.status_code, 200)

    def test_path_traversal_is_rejected(self):
        res = fetch(cookie_client(make_admin()), "/media/../manage.py")
        self.assertEqual(res.status_code, 404)


class OriginCheckTests(TestCase):
    def setUp(self):
        self.user = make_user("client")

    def test_cross_site_write_with_auth_cookie_is_blocked(self):
        res = cookie_client(self.user).post("/api/logout/", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(res.status_code, 403)

    def test_allowed_origin_and_non_browser_clients_pass(self):
        res = cookie_client(self.user).post("/api/logout/", HTTP_ORIGIN="http://localhost:3000")
        self.assertEqual(res.status_code, 200)
        res = cookie_client(self.user).post("/api/logout/")
        self.assertEqual(res.status_code, 200)

    def test_cross_site_reads_are_not_affected(self):
        res = cookie_client(self.user).get("/api/notifications/", HTTP_ORIGIN="https://evil.example")
        self.assertEqual(res.status_code, 200)


class PaginationTests(TestCase):
    def test_page_size_query_param(self):
        user = make_user("client")
        for i in range(7):
            notify_user(user, "SYSTEM", f"n{i}")
        api = APIClient()
        api.force_authenticate(user)
        res = api.get("/api/notifications/?page_size=5")
        self.assertEqual(len(res.data["results"]), 5)
        self.assertEqual(res.data["count"], 7)
        self.assertEqual(len(api.get("/api/notifications/").data["results"]), 7)


class StripeWebhookTests(TestCase):
    def setUp(self):
        self.client_user = make_user("client")
        freelancer = make_freelancer()
        proposal = make_proposal(make_project(self.client_user), freelancer, status="accepted")
        self.offer = make_offer(proposal, total_budget="250.00")

    def test_amount_mismatch_does_not_fund_escrow(self):
        StripeEscrowProcessor().process(
            offer_id=self.offer.id, payment_intent_id="pi_1", amount_total=100
        )
        self.assertFalse(EscrowPayment.objects.filter(offer=self.offer).exists())

    def test_matching_amount_funds_escrow_and_creates_contract(self):
        StripeEscrowProcessor().process(
            offer_id=self.offer.id, payment_intent_id="pi_2", amount_total=25000
        )
        self.assertEqual(EscrowPayment.objects.get(offer=self.offer).amount, Decimal("250.00"))
        self.assertTrue(Contract.objects.filter(offer=self.offer).exists())
        # Replays are ignored
        StripeEscrowProcessor().process(
            offer_id=self.offer.id, payment_intent_id="pi_3", amount_total=25000
        )
        self.assertEqual(EscrowPayment.objects.filter(offer=self.offer).count(), 1)

    def test_unpaid_session_is_ignored(self):
        event = {
            "type": "checkout.session.completed",
            "data": {"object": {
                "id": "cs_1", "payment_status": "unpaid", "payment_intent": "pi_4",
                "amount_total": 25000,
                "metadata": {"payment_type": "escrow", "offer_id": str(self.offer.id)},
            }},
        }
        with mock.patch("apps.users.views.stripe.Webhook.construct_event", return_value=event):
            res = APIClient().post("/api/stripe-webhook/", data=b"{}", content_type="application/json")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(EscrowPayment.objects.filter(offer=self.offer).exists())


class PublicProjectTests(TestCase):
    def test_open_projects_hide_client_email(self):
        make_project(make_user("client"))
        api = APIClient()
        api.force_authenticate(make_freelancer())
        res = api.get("/api/freelancer-projects/open/")
        self.assertEqual(res.status_code, 200)
        client = res.data["results"][0]["client"]
        self.assertNotIn("email", client)
        self.assertIn("username", client)


class AdminDeleteTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_delete_user_without_history(self):
        user = make_freelancer()
        res = self.api.delete(f"/api/users/{user.id}/")
        self.assertEqual(res.status_code, 204)

    def test_users_with_contracts_are_protected(self):
        contract = make_active_contract()
        res = self.api.delete(f"/api/users/{contract.get_freelancer_user().id}/")
        self.assertEqual(res.status_code, 400)
        res = self.api.delete(f"/api/admin-projects/{contract.offer.proposal.project.id}/")
        self.assertEqual(res.status_code, 400)

    def test_cannot_delete_self_and_non_admin_cannot_delete(self):
        self.assertEqual(self.api.delete(f"/api/users/{self.admin.id}/").status_code, 400)
        other = APIClient()
        other.force_authenticate(make_user("client"))
        self.assertEqual(other.delete(f"/api/users/{self.admin.id}/").status_code, 403)

    def test_delete_project_without_contract(self):
        project = make_project(make_user("client"))
        self.assertEqual(self.api.delete(f"/api/admin-projects/{project.id}/").status_code, 204)


class OfferEmailTests(TestCase):
    def test_offer_creation_emails_the_freelancer(self):
        client_user = make_user("client")
        freelancer = make_freelancer()
        proposal = make_proposal(make_project(client_user), freelancer, status="accepted")
        api = APIClient()
        api.force_authenticate(client_user)
        with self.captureOnCommitCallbacks(execute=True):
            res = api.post(
                "/api/offers/create/",
                {
                    "proposal": proposal.id,
                    "total_budget": "500.00",
                    "agreed_hourly_rate": "25.00",
                    "estimated_hours": 10,
                    "valid_until": (timezone.now() + timedelta(days=3)).isoformat(),
                },
                format="json",
            )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [freelancer.email])
        self.assertIn("₹25.00/hr", message.body)
        self.assertIn("/freelancer/offers-list/", message.body)
