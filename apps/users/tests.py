from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.adminpanel.models import SubscriptionPlan
from apps.cores.factories import PASSWORD, make_freelancer, make_project, make_user
from apps.users.models import User, UserSubscription
from apps.users.utils import MAX_OTP_ATTEMPTS, create_and_send_otp, generate_otp, verify_otp


class OTPTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_generate_otp_is_numeric_with_requested_length(self):
        otp = generate_otp(6)
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    def test_otp_is_single_use(self):
        otp = create_and_send_otp("a@example.com", purpose="register", send_async=False)
        self.assertTrue(verify_otp("A@example.com ", otp, purpose="register"))
        self.assertFalse(verify_otp("a@example.com", otp, purpose="register"))

    def test_otp_is_burned_after_too_many_wrong_guesses(self):
        otp = create_and_send_otp("b@example.com", purpose="register", send_async=False)
        wrong = "000000" if otp != "000000" else "111111"
        for _ in range(MAX_OTP_ATTEMPTS):
            self.assertFalse(verify_otp("b@example.com", wrong, purpose="register"))
        # Even the right code no longer works once the OTP was invalidated
        self.assertFalse(verify_otp("b@example.com", otp, purpose="register"))


class PasswordResetTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = make_user("client", email="reset@example.com")

    def _reset_payload(self, **extra):
        payload = {
            "email": "reset@example.com",
            "new_password": "N3w!Password",
            "confirm_new_password": "N3w!Password",
        }
        payload.update(extra)
        return payload

    def test_reset_without_verified_otp_is_rejected(self):
        # Previously this alone reset any account's password
        res = self.client.post("/api/reset-password/", self._reset_payload(), format="json")
        self.assertEqual(res.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_reset_with_forged_token_is_rejected(self):
        res = self.client.post(
            "/api/reset-password/", self._reset_payload(reset_token="forged"), format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_full_reset_flow(self):
        with mock.patch("apps.users.utils.send_otp_email.delay") as delay:
            res = self.client.post("/api/forgot-password/", {"email": "reset@example.com"}, format="json")
        self.assertEqual(res.status_code, 200)
        otp = delay.call_args.args[1]

        res = self.client.post(
            "/api/verify-reset-otp/", {"email": "reset@example.com", "otp": otp}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        token = res.data["reset_token"]

        res = self.client.post(
            "/api/reset-password/", self._reset_payload(reset_token=token), format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("N3w!Password"))

        # Token is single use
        res = self.client.post(
            "/api/reset-password/", self._reset_payload(reset_token=token), format="json"
        )
        self.assertEqual(res.status_code, 400)


class RegistrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_verify_otp_enforces_password_strength(self):
        otp = create_and_send_otp("new@example.com", purpose="register", send_async=False)
        res = self.client.post(
            "/api/verify-otp/",
            {"email": "new@example.com", "username": "new", "role": "client",
             "password": "weak", "otp": otp},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.data)
        self.assertFalse(User.objects.filter(email="new@example.com").exists())

    def test_verify_otp_creates_user(self):
        otp = create_and_send_otp("new2@example.com", purpose="register", send_async=False)
        res = self.client.post(
            "/api/verify-otp/",
            {"email": "New2@Example.com", "username": "new2", "role": "freelancer",
             "password": PASSWORD, "otp": otp},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(User.objects.get(email="new2@example.com").role, "freelancer")


class AuthCookieTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("client", email="login@example.com")

    def test_login_sets_httponly_cookies(self):
        res = self.client.post(
            "/api/login/", {"email": "login@example.com", "password": PASSWORD}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.cookies["access_token"]["httponly"])
        self.assertTrue(res.cookies["refresh_token"]["httponly"])
        self.assertEqual(res.data["user"]["role"], "client")

    def test_cookie_authentication_end_to_end(self):
        # Real CookieJWTAuthentication path (no force_authenticate)
        self.assertEqual(self.client.get("/api/client/statistics/").status_code, 401)
        self.client.post(
            "/api/login/", {"email": "login@example.com", "password": PASSWORD}, format="json"
        )
        res = self.client.get("/api/client/statistics/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["escrow_balance"], 0)

        res = self.client.post("/api/logout/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.cookies["access_token"].value, "")

    def test_blocked_user_access_token_is_rejected(self):
        self.client.post(
            "/api/login/", {"email": "login@example.com", "password": PASSWORD}, format="json"
        )
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.client.get("/api/client/statistics/").status_code, 401)

    def test_refresh_rejected_for_blocked_user(self):
        res = self.client.post(
            "/api/login/", {"email": "login@example.com", "password": PASSWORD}, format="json"
        )
        refresh = res.cookies["refresh_token"].value
        self.user.is_active = False
        self.user.save()
        self.client.cookies["refresh_token"] = refresh
        res = self.client.post("/api/refresh-token/")
        self.assertEqual(res.status_code, 401)

    def test_google_login_sets_cookies_and_returns_user(self):
        idinfo = {"iss": "accounts.google.com", "email": "login@example.com", "email_verified": True}
        with mock.patch("apps.users.views.id_token.verify_oauth2_token", return_value=idinfo):
            res = self.client.post(
                "/api/google-login/", {"id_token": "tok", "timezone": "Asia/Kolkata"}, format="json"
            )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["user"]["email"], "login@example.com")
        self.assertIn("access_token", res.cookies)
        self.assertNotIn("access", res.data)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_detected_timezone, "Asia/Kolkata")

    def test_google_login_rejects_unverified_email(self):
        idinfo = {"iss": "accounts.google.com", "email": "login@example.com", "email_verified": False}
        with mock.patch("apps.users.views.id_token.verify_oauth2_token", return_value=idinfo):
            res = self.client.post("/api/google-login/", {"id_token": "tok"}, format="json")
        self.assertEqual(res.status_code, 400)


class ClientEndpointsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("client")
        self.plan = SubscriptionPlan.objects.create(
            name="Basic", price=Decimal("499.00"), max_projects=2, duration_days=30
        )

    def test_statistics_requires_authentication(self):
        res = self.client.get("/api/client/statistics/")
        self.assertEqual(res.status_code, 401)

    def test_client_cannot_set_own_rating(self):
        self.client.force_authenticate(self.user)
        res = self.client.post(
            "/api/profile/", {"company_name": "Acme", "rating": "5.00"}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(Decimal(res.data["rating"]), Decimal("0.00"))

    def _project_payload(self, **extra):
        payload = {
            "title": "Build an API",
            "description": "A sufficiently long project description.",
            "skills_required": [],
            "budget_type": "fixed",
            "fixed_budget": "1000.00",
            "experience_level": "entry",
            "duration": "1 month",
        }
        payload.update(extra)
        return payload

    def test_project_rejects_non_positive_fixed_budget(self):
        UserSubscription.objects.create(user=self.user, plan=self.plan).activate()
        self.client.force_authenticate(self.user)
        res = self.client.post("/api/projects/", self._project_payload(fixed_budget="-5"), format="json")
        self.assertEqual(res.status_code, 400)

    def test_project_creation_consumes_subscription_slot(self):
        sub = UserSubscription.objects.create(user=self.user, plan=self.plan)
        sub.activate()
        self.client.force_authenticate(self.user)
        res = self.client.post("/api/projects/", self._project_payload(), format="json")
        self.assertEqual(res.status_code, 201, res.data)
        sub.refresh_from_db()
        self.assertEqual(sub.remaining_projects, 1)

    def test_partial_update_cannot_invert_hourly_range(self):
        project = make_project(self.user)  # hourly 10-50
        self.client.force_authenticate(self.user)
        res = self.client.patch(
            f"/api/projects/{project.id}/", {"hourly_min_rate": "80.00"}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_freelancer_profile_detail_still_works(self):
        freelancer = make_freelancer()
        self.client.force_authenticate(self.user)
        res = self.client.get(f"/api/freelancer-profile/{freelancer.id}/")
        self.assertEqual(res.status_code, 200)
