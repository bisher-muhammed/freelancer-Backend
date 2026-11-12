from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.applications.models import ChatRoom, Meeting, Offer, ProposalScore
from apps.applications.services.proposal_scoring_service import ProposalScoringService
from apps.cores.factories import (
    make_freelancer,
    make_offer,
    make_project,
    make_proposal,
    make_user,
)


class ScoringTests(TestCase):
    def setUp(self):
        self.client_user = make_user("client")
        self.freelancer = make_freelancer(is_verified=True)

    def test_over_budget_bid_is_scored_without_crashing(self):
        # Decimal budget-fit * float weight used to raise TypeError (500)
        project = make_project(self.client_user, hourly_max_rate=Decimal("50.00"))
        proposal = make_proposal(project, self.freelancer, bid_hourly_rate=Decimal("60.00"))
        score = ProposalScoringService.score_proposal(proposal)
        # 20% over the max rate -> 70 - 20 = 50
        self.assertAlmostEqual(score.budget_fit, 50.0)

    def test_budget_fit_boundaries(self):
        fit = ProposalScoringService._calculate_budget_fit
        project = make_project(self.client_user, budget_type="fixed",
                               fixed_budget=Decimal("100.00"),
                               hourly_min_rate=None, hourly_max_rate=None)
        cases = [("50.00", 100.0), ("100.00", 100.0), ("110.00", 60.0), ("200.00", 0.0), ("1000.00", 0.0)]
        for bid, expected in cases:
            proposal = mock.Mock(bid_fixed_price=Decimal(bid))
            self.assertAlmostEqual(fit(project, proposal), expected, msg=bid)

    def test_final_score_uses_weights(self):
        # No config row exists -> model defaults (0.4/0.3/0.2/0.1)
        project = make_project(self.client_user)  # no required skills -> 100
        proposal = make_proposal(project, self.freelancer, bid_hourly_rate=Decimal("20.00"))
        score = ProposalScoringService.score_proposal(proposal)
        # skills 100*.4 + exp 0*.3 + budget 100*.2 + reliability 100*.1 = 70
        self.assertAlmostEqual(score.final_score, 70.0)
        self.assertFalse(score.auto_reject)


class ProposalApplyTests(TestCase):
    def setUp(self):
        self.client_user = make_user("client")
        self.project = make_project(self.client_user)
        self.api = APIClient()

    def _apply(self, user, **extra):
        self.api.force_authenticate(user)
        payload = {"project": self.project.id, "cover_letter": "x" * 150, "bid_hourly_rate": "25.00"}
        payload.update(extra)
        return self.api.post("/api/proposal/apply/", payload, format="json")

    def test_freelancer_can_apply_and_proposal_is_scored(self):
        res = self._apply(make_freelancer())
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(ProposalScore.objects.count(), 1)

    def test_client_cannot_apply(self):
        res = self._apply(make_user("client"))
        self.assertEqual(res.status_code, 400)

    def test_negative_bid_rejected(self):
        res = self._apply(make_freelancer(), bid_hourly_rate="-10.00")
        self.assertEqual(res.status_code, 400)


class OfferTests(TestCase):
    def setUp(self):
        self.client_user = make_user("client")
        self.freelancer = make_freelancer()
        project = make_project(self.client_user)
        self.proposal = make_proposal(project, self.freelancer, status="accepted")
        self.api = APIClient()

    def test_expired_offer_can_still_be_rejected(self):
        offer = make_offer(self.proposal, status="pending")
        Offer.objects.filter(id=offer.id).update(valid_until=timezone.now() - timedelta(days=1))
        self.api.force_authenticate(self.freelancer)
        res = self.api.patch(f"/api/offers/{offer.id}/reject/", {}, format="json")
        self.assertEqual(res.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, "rejected")

    def test_other_freelancer_cannot_accept_offer(self):
        offer = make_offer(self.proposal, status="pending")
        self.api.force_authenticate(make_freelancer())
        res = self.api.patch(f"/api/offers/{offer.id}/accept/", {}, format="json")
        self.assertEqual(res.status_code, 400)
        offer.refresh_from_db()
        self.assertEqual(offer.status, "pending")

    def test_freelancer_offer_list_without_profile_is_empty_not_500(self):
        self.api.force_authenticate(make_user("freelancer"))
        res = self.api.get("/api/offers/freelancer/")
        self.assertEqual(res.status_code, 200)


class MeetingTests(TestCase):
    def setUp(self):
        self.client_user = make_user("client")
        self.freelancer = make_freelancer()
        project = make_project(self.client_user)
        self.proposal = make_proposal(project, self.freelancer, status="shortlisted")
        self.chat = ChatRoom.objects.create(
            project=project, proposal=self.proposal,
            client=self.client_user, freelancer=self.freelancer,
        )
        now = timezone.now()
        self.meeting = Meeting.objects.create(
            proposal=self.proposal, chat_room=self.chat, created_by=self.client_user,
            meeting_type="interview", start_time=now - timedelta(minutes=1),
            end_time=now + timedelta(minutes=30), status="ongoing",
        )
        self.api = APIClient()

    @mock.patch("apps.applications.video_token.generate_zego_token", return_value="tok")
    def test_ongoing_meeting_still_issues_join_tokens(self, _gen):
        self.api.force_authenticate(self.freelancer)
        with self.settings(APPID="1", ZEGO_SERVER_URL="wss://zego"):
            res = self.api.post("/api/meeting/zego-token/", {"meeting_id": self.meeting.id}, format="json")
        self.assertEqual(res.status_code, 200, res.data)

    def test_update_cannot_repoint_meeting_to_another_proposal(self):
        other_project = make_project(self.client_user)
        other_proposal = make_proposal(other_project, make_freelancer(), status="shortlisted")
        self.api.force_authenticate(self.client_user)
        res = self.api.patch(
            f"/api/meetings/{self.meeting.id}/", {"proposal": other_proposal.id}, format="json"
        )
        self.assertEqual(res.status_code, 400)

    def test_mark_read_reports_marked_count(self):
        self.chat.messages.create(sender=self.freelancer, content="hi")
        self.api.force_authenticate(self.client_user)
        res = self.api.post(f"/api/chat/{self.chat.id}/mark-read/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("1 messages", res.data["detail"])
