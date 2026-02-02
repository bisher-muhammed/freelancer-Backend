from django.conf import settings
from rest_framework import generics,permissions,status,viewsets
from rest_framework.response import Response
from apps.notifications.services.create_notifications import notify_user
from apps. users.models import Project
from.models import EscrowPayment, Offer, Proposal,SavedProject,Meeting
from.serializers import MeetingPublicSerializer, OfferAcceptSerializer, OfferCreateSerializer, OfferReadOnlySerializer, OfferRejectSerializer, ProjectDetailSerializer,ProposalCreateSerializer,MyProposalSerializer,ProposalDetailSerializer
from apps.applications.services.proposal_scoring_service import ProposalScoringService
from rest_framework.permissions import IsAuthenticated
from apps.applications.models import FreelancerProfile
from rest_framework.decorators import action
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction
from apps.applications.tasks import send_meeting_created_email
import stripe
from decimal import Decimal,ROUND_HALF_UP


from rest_framework import generics, permissions
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from django.shortcuts import get_object_or_404
from apps.applications.models import ChatRoom, Message
from apps.applications.serializers import (
    ChatRoomCreateSerializer,
    ClientChatRoomSerializer,
    FreelancerChatRoomSerializer,
    MessageSerializer,
    SavedProjectListSerializer,
    ToggleSaveProjectSerializer,
    MeetingSerializer
)
from .permissions import IsChatParticipant, IsClient, IsClientOwnerOfProposal,IsClientParticipant, IsFreelancer
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction



stripe.api_key = settings.STRIPE_SECRET_KEY
class ProjectDetailView(generics.RetrieveAPIView):
    ''''
    Retrive details of a single project including skills and client info.
    Also returns whether the current freelancer already applied
    '''

    queryset = Project.objects.all()
    serializer_class = ProjectDetailSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = 'id'



class ProposalCreateView(generics.CreateAPIView):
    """
    Freelancer submits a proposal.

    Flow:
    1. Save proposal
    2. Score proposal
    3. Send notifications
    """

    serializer_class = ProposalCreateSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        proposal = serializer.save()

        freelancer = proposal.freelancer
        project = proposal.project
        client = project.client

        # ✅ Step 1: Score proposal
        ProposalScoringService.score_proposal(proposal)

        # ✅ Step 2: Notify Freelancer
        notify_user(
            recipient=freelancer,
            notif_type="PROPOSAL_SUBMITTED",
            title="Proposal Submitted",
            message=f"You successfully applied to '{project.title}'.",
            data={
                "proposal_id": proposal.id,
                "project_id": project.id,
            },
        )

        # ✅ Step 3: Notify Client
        notify_user(
            recipient=client,
            notif_type="PROPOSAL_SUBMITTED",
            title="New Proposal Received",
            message=f"{freelancer.username} submitted a proposal for '{project.title}'.",
            data={
                "proposal_id": proposal.id,
                "project_id": project.id,
                "freelancer_id": freelancer.id,
            },
        )

        return proposal

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)

        return Response(
            {"detail": "Application submitted successfully."},
            status=status.HTTP_201_CREATED,
        )




class MyProposals(generics.ListAPIView):
    serializer_class = MyProposalSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Proposal.objects
            .select_related('project', 'project__client')
            .prefetch_related('project__skills_required')
            .filter(freelancer=self.request.user)
            .order_by('-created_at')
        )







# -------------------------
# 1. Client: Create Chat Room
# -------------------------
class ChatRoomGetOrCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsClientOwnerOfProposal]

    def post(self, request):
        proposal_id = request.data.get("proposal")

        if not proposal_id:
            return Response(
                {"detail": "proposal is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        proposal = get_object_or_404(Proposal, id=proposal_id)

        chat_room, created = ChatRoom.objects.get_or_create(
            proposal=proposal,
            defaults={
                "client": request.user,
                "freelancer": proposal.freelancer,
                "project": proposal.project,
            }
        )

        return Response(
            {
                "chat_id": chat_room.id,
                "created": created
            },
            status=status.HTTP_200_OK
        )

# -------------------------
# 2. Client: List Chat Rooms
# -------------------------
class ClientChatRoomListView(generics.ListAPIView):
    serializer_class = ClientChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatRoom.objects.filter(client=self.request.user).order_by("-created_at")


# -------------------------
# 3. Freelancer: List Chat Rooms
# -------------------------
class FreelancerChatRoomListView(generics.ListAPIView):
    serializer_class = FreelancerChatRoomSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ChatRoom.objects.filter(freelancer=self.request.user).order_by("-created_at")


# -------------------------
# 4. Message List / One-to-One Chat
# -------------------------
class MessageListView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated, IsChatParticipant]

    def get_chat(self):
        chat_id = self.kwargs.get("chat_id")
        chat = get_object_or_404(ChatRoom, id=chat_id)
        self.check_object_permissions(self.request, chat)
        return chat

    def get_queryset(self):
        chat = self.get_chat()
        return chat.messages.all().order_by("created_at")

    def perform_create(self, serializer):
        chat = self.get_chat()
        serializer.save(
            sender=self.request.user,
            chat_room=chat
        )



class MarkChatAsReadView(APIView):
    permission_classes = [IsAuthenticated, IsChatParticipant]

    def post(self, request, chat_id):
        # Get chat and check permissions
        chat = get_object_or_404(ChatRoom, id=chat_id)
        self.check_object_permissions(request, chat)

        # Mark messages as read where receiver is current user
        messages_to_mark = chat.messages.filter(is_read=False).exclude(sender=request.user)
        messages_to_mark.update(is_read=True)

        return Response(
            {"detail": f"{messages_to_mark.count()} messages marked as read."},
            status=status.HTTP_200_OK
        )




class ToggleSaveProjectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            freelancer = FreelancerProfile.objects.get(user=request.user)
        except FreelancerProfile.DoesNotExist:
            return Response(
                {"detail": "Freelancer profile not found."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ToggleSaveProjectSerializer(
            data=request.data,
            context={"freelancer": freelancer}
        )
        serializer.is_valid(raise_exception=True)
        result = serializer.save()

        return Response(result, status=status.HTTP_200_OK)


class SavedProjectListView(generics.ListAPIView):
    serializer_class = SavedProjectListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        freelancer = FreelancerProfile.objects.get(user=self.request.user)

        return (
            SavedProject.objects
            .filter(freelancer=freelancer)
            .select_related("project")
            .order_by("-saved_at")
        )






class MeetingViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]

    # -------------------------
    # Queryset
    # -------------------------
    def get_queryset(self):
        user = self.request.user
        return Meeting.objects.filter(
            Q(chat_room__client=user) |
            Q(chat_room__freelancer=user)
        )

    # -------------------------
    # Serializer selection
    # -------------------------
    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return MeetingPublicSerializer
        return MeetingSerializer

    # -------------------------
    # Permissions
    # -------------------------
    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsClientOwnerOfProposal()]

        if self.action in [
            "update",
            "partial_update",
            "destroy",
            "cancel_meeting",
            "mark_ongoing",
            "mark_completed",
        ]:
            return [permissions.IsAuthenticated(), IsClientParticipant()]

        return [permissions.IsAuthenticated()]

    # -------------------------
    # Hooks
    # -------------------------
    def perform_create(self, serializer):
        with transaction.atomic():
            meeting = serializer.save(created_by=self.request.user)

            proposal = meeting.proposal

            if (
                meeting.meeting_type == "interview"
                and proposal.status == "shortlisted"
            ):
                proposal.status = "interviewing"
                proposal.save(update_fields=["status"])

            send_meeting_created_email.delay(meeting.id)

    # -------------------------
    # State transitions
    # -------------------------
    @action(detail=True, methods=["post"])
    def mark_ongoing(self, request, pk=None):
        meeting = self.get_object()
        meeting.mark_ongoing()
        return Response({"status": meeting.status})

    @action(detail=True, methods=["post"])
    def mark_completed(self, request, pk=None):
        meeting = self.get_object()
        meeting.mark_completed()
        return Response({"status": meeting.status})

    @action(detail=True, methods=["post"])
    def cancel_meeting(self, request, pk=None):
        meeting = self.get_object()
        meeting.cancel()
        return Response({"status": meeting.status})


class FreelancerProposalDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProposalDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return (
            Proposal.objects
            .select_related("project", "project__client")
            .prefetch_related("meetings")
            .filter(freelancer=self.request.user)
        )




class OfferCreateView(generics.CreateAPIView):
    serializer_class = OfferCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsClient]

    def get_queryset(self):
        # Not really used, but DRF expects it
        return Offer.objects.none()

class ClientOfferListView(generics.ListAPIView):
    serializer_class = OfferReadOnlySerializer
    permission_classes = [permissions.IsAuthenticated, IsClient]

    def get_queryset(self):
        return Offer.objects.filter(
            client=self.request.user
        ).select_related(
            "proposal",
            "client",
            "freelancer",
            "proposal__project"
        ).order_by("-created_at")


class ClientOfferDetailView(generics.RetrieveAPIView):
    serializer_class = OfferReadOnlySerializer
    permission_classes = [permissions.IsAuthenticated, IsClient]
    lookup_field = "id"

    def get_queryset(self):
        return Offer.objects.filter(client=self.request.user)






class FreelancerOfferListView(generics.ListAPIView):
    serializer_class = OfferReadOnlySerializer
    permission_classes = [permissions.IsAuthenticated, IsFreelancer]

    def get_queryset(self):
        freelancer_profile = FreelancerProfile.objects.get(
            user=self.request.user
        )

        return (
            Offer.objects
            .filter(freelancer=freelancer_profile)
            .select_related(
                "proposal",
                "client",
                "proposal__project"
            )
            .order_by("-created_at")
        )


class FreelancerOfferDetailView(generics.RetrieveAPIView):
    serializer_class = OfferReadOnlySerializer
    permission_classes = [permissions.IsAuthenticated, IsFreelancer]
    lookup_field = "id"

    def get_queryset(self):
        freelancer_profile = FreelancerProfile.objects.get(
            user=self.request.user
        )

        return Offer.objects.filter(freelancer=freelancer_profile)
    


class CreateEscrowCheckoutSession(APIView):
    permission_classes = [IsAuthenticated]
    MINIMUM_AMOUNT_CENTS = 50

    def post(self, request):
        offer_id = request.data.get("offer_id")

        with transaction.atomic():
            offer = get_object_or_404(
                Offer.objects.select_for_update(),
                id=offer_id,
                client=request.user
            )

            if offer.status != "accepted":
                return Response(
                    {"detail": "Offer must be accepted first."},
                    status=400
                )

            if hasattr(offer, "payment"):
                return Response(
                    {"detail": "Payment already initiated."},
                    status=400
                )

            amount_cents = int(
                (offer.total_budget * 100).quantize(
                    Decimal("1"), rounding=ROUND_HALF_UP
                )
            )

            if amount_cents < self.MINIMUM_AMOUNT_CENTS:
                return Response(
                    {"detail": "Amount below Stripe minimum."},
                    status=400
                )

            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                mode="payment",
                line_items=[
                    {
                        "price_data": {
                            "currency": "inr",
                            "product_data": {
                                "name": f"Escrow for Project #{offer.proposal.project.id}",
                            },
                            "unit_amount": amount_cents,
                        },
                        "quantity": 1,
                    }
                ],
                metadata={
                    "offer_id": str(offer.id),
                },
                success_url="http://localhost:3000/payment-success",
                cancel_url="http://localhost:3000/payment-failed",
            )

            EscrowPayment.objects.create(
                offer=offer,
                amount=offer.total_budget,
                status="pending",
            )

        return Response(
            {
                "checkout_url": session.url,
                "session_id": session.id,
            },
            status=201
        )



class OfferAcceptView(generics.UpdateAPIView):
    serializer_class = OfferAcceptSerializer
    permission_classes = [permissions.IsAuthenticated, IsFreelancer]
    queryset = Offer.objects.select_related("proposal", "freelancer")
    lookup_field = "id"

    def perform_update(self, serializer):
        offer = serializer.save(status="accepted")

        proposal = offer.proposal
        proposal.status = "accepted"
        proposal.save(update_fields=["status"])

        freelancer = proposal.freelancer
        client = proposal.project.client
        project = proposal.project

        # ✅ Notify Freelancer
        notify_user(
            recipient=freelancer,
            notif_type="OFFER_ACCEPTED",
            title="Offer Accepted",
            message=f"You accepted the offer for '{project.title}'.",
            data={"offer_id": offer.id}
        )

        # ✅ Notify Client
        notify_user(
            recipient=client,
            notif_type="OFFER_ACCEPTED",
            title="Offer Accepted 🎉",
            message=f"{freelancer.username} accepted your offer for '{project.title}'.",
            data={"offer_id": offer.id}
        )

    



class OfferRejectView(generics.UpdateAPIView):
    serializer_class = OfferRejectSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Offer.objects.all()
    lookup_field = "id"

    def perform_update(self, serializer):
        serializer.save(status="rejected")

