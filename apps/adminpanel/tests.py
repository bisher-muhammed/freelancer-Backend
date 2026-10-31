from django.test import TestCase
from rest_framework.test import APIClient

from apps.adminpanel.models import TrackingPolicy
from apps.cores.factories import make_active_contract, make_admin, make_freelancer, make_user
from apps.freelancer.models import Skill


class AdminPermissionTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.target = make_user("client")
        self.freelancer = make_freelancer()

    def test_anonymous_cannot_block_users(self):
        res = self.api.post("/api/toggle_block/", {"user_id": self.target.id}, format="json")
        self.assertEqual(res.status_code, 401)
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_regular_user_cannot_block_or_verify(self):
        self.api.force_authenticate(make_user("client"))
        res = self.api.post("/api/toggle_block/", {"user_id": self.target.id}, format="json")
        self.assertEqual(res.status_code, 403)
        res = self.api.post(f"/api/freelancers/{self.freelancer.id}/verify/")
        self.assertEqual(res.status_code, 403)
        res = self.api.get(f"/api/freelancers/{self.freelancer.id}/")
        self.assertEqual(res.status_code, 403)
        self.freelancer.freelancer_profile.refresh_from_db()
        self.assertFalse(self.freelancer.freelancer_profile.is_verified)

    def test_admin_can_block_and_verify(self):
        admin = make_admin()
        self.api.force_authenticate(admin)
        res = self.api.post("/api/toggle_block/", {"user_id": self.target.id}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["is_active"])
        res = self.api.post(f"/api/freelancers/{self.freelancer.id}/verify/")
        self.assertEqual(res.status_code, 200)
        res = self.api.post("/api/toggle_block/", {"user_id": admin.id}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_verify_missing_freelancer_is_404(self):
        self.api.force_authenticate(make_admin())
        res = self.api.post("/api/freelancers/999999/verify/")
        self.assertEqual(res.status_code, 404)


class SkillPermissionTests(TestCase):
    def test_users_can_add_but_not_delete_skills(self):
        skill = Skill.objects.create(name="Django")
        api = APIClient()
        api.force_authenticate(make_user("client"))
        self.assertEqual(api.post("/api/skills/", {"name": "React"}, format="json").status_code, 201)
        self.assertEqual(api.delete(f"/api/skills/{skill.id}/").status_code, 403)
        self.assertTrue(Skill.objects.filter(id=skill.id).exists())


class TrackingPolicyAdminTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(make_admin())
        self.policy = TrackingPolicy.objects.create(version="1.0", title="T", content="C")

    def test_update_and_delete_endpoints(self):
        res = self.api.patch(
            f"/api/admin-tracking-policy/update/{self.policy.id}", {"title": "New"}, format="json"
        )
        self.assertEqual(res.status_code, 200)
        res = self.api.delete(f"/api/admin/tracking-privacy/delete/{self.policy.id}")
        self.assertEqual(res.status_code, 204)

    def test_delete_policy_in_use_returns_400(self):
        contract = make_active_contract()
        contract.tracking_policy = self.policy
        contract.save()
        res = self.api.delete(f"/api/admin/tracking-privacy/delete/{self.policy.id}")
        self.assertEqual(res.status_code, 400)
