from unittest import mock

from django.test import TestCase
from rest_framework.test import APIClient

from apps.cores.factories import make_user
from apps.notifications.models import Notification
from apps.notifications.services.create_notifications import notify_user


class NotificationTests(TestCase):
    def setUp(self):
        self.user = make_user("client")
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_notify_survives_channel_layer_outage(self):
        with mock.patch(
            "apps.notifications.services.create_notifications.get_channel_layer",
            side_effect=ConnectionError("redis down"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                notif = notify_user(self.user, "PROFILE_UPDATED", "Hi")
        self.assertTrue(Notification.objects.filter(id=notif.id).exists())

    def test_list_and_mark_read(self):
        notif = notify_user(self.user, "PROFILE_UPDATED", "Hi")
        res = self.api.get("/api/notifications/")
        self.assertEqual(res.status_code, 200)
        res = self.api.post(f"/api/notifications/{notif.id}/read/")
        self.assertEqual(res.status_code, 204)
        notif.refresh_from_db()
        self.assertTrue(notif.is_read)

    def test_users_cannot_create_notifications(self):
        res = self.api.post("/api/notifications/", {"title": "spoof", "notif_type": "X"}, format="json")
        self.assertEqual(res.status_code, 405)

    def test_cannot_read_other_users_notification(self):
        other = notify_user(make_user("client"), "PROFILE_UPDATED", "Secret")
        res = self.api.get(f"/api/notifications/{other.id}/")
        self.assertEqual(res.status_code, 404)
