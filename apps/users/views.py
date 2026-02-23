import logging
import stripe
import traceback
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import OuterRef, Subquery, FloatField, BooleanField
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework import status, generics, viewsets, permissions
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import Count, Sum
from apps.adminpanel.models import SubscriptionPlan
from apps.adminpanel.serializers import SubscriptionPlanSerializer
from apps.applications.models import EscrowPayment, Proposal, ProposalScore
from apps.contract.models import Contract
from apps.finance.models import LedgerEntry
from apps.freelancer.models import FreelancerProfile
from apps.freelancer.serializers import FreelancerProfileSerializer
from apps.users.payments.processors import StripeEscrowProcessor, StripeSubscriptionProcessor
from .models import ClientProfile, Project, UserSubscription
from .serializers import (
    CompletedProjectSerializer,
    ProjectSerializer,
    SendOTPSerializer,
    RegisterFormSerializer,
    VerifyOTPSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    VerifyPasswordResetOTPSerializer,
    ResetPasswordSerializer,
    ClientProfileSerializer,
    ClientProposalSerializer,
    ProposalStatusUpdateSerializer,
    CreatePaymentSerializer,
    UserSubscriptionSerializer,
)

User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)


class SendOTPView(generics.GenericAPIView):
    serializer_class = SendOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "OTP sent successfully.",
                    "data": result,
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class RegisterView(generics.GenericAPIView):
    serializer_class = RegisterFormSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            return Response(
                {
                    "success": True,
                    "message": "Form submitted successfully. Please verify OTP to complete registration.",
                    "data": serializer.validated_data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyOTPView(generics.GenericAPIView):
    serializer_class = VerifyOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "User registered successfully.",
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                        "role": user.role,
                    },
                },
                status=status.HTTP_201_CREATED,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {
                "success": True,
                "message": "Login successful.",
                "data": serializer.validated_data
            },
            status=status.HTTP_200_OK
        )

class ForgotPasswordView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "If the email exists, a password reset OTP has been sent.",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class VerifyPasswordResetOTPView(generics.GenericAPIView):
    serializer_class = VerifyPasswordResetOTPSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            return Response(
                {
                    "success": True,
                    "message": "OTP verified successfully. You may now reset your password.",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "success": True,
                    "message": "Password reset successfully.",
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    token = request.data.get("id_token")

    if not token:
        return Response({
            "success": False,
            "message": "Token is required"
        }, status=400)

    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )

        if idinfo['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
            return Response({
                "success": False,
                "message": "Invalid token issuer"
            }, status=400)

        email = idinfo.get("email")

        if not email:
            return Response({
                "success": False,
                "message": "Email not found in Google data"
            }, status=400)

    except ValueError as e:
        return Response({
            "success": False,
            "message": "Invalid Google token",
            "error": str(e)
        }, status=400)
    except Exception as e:
        traceback.print_exc()
        return Response({
            "success": False,
            "message": "Token verification failed",
            "error": str(e)
        }, status=400)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({
            "success": False,
            "message": "Email not registered. Please register using password first."
        }, status=404)

    try:
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
    except Exception:
        return Response({
            "success": False,
            "message": "Failed to generate tokens"
        }, status=500)

    return Response({
        "success": True,
        "message": "Login successful.",
        "data": {
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role,
            },
            "access": access_token,
            "refresh": refresh_token,
        }
    })


class ClientProfileViewSet(viewsets.ModelViewSet):
    serializer_class = ClientProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ClientProfile.objects.filter(user=self.request.user)

    @action(detail=False, methods=['patch'])
    def update_profile(self, request):
        profile, _ = ClientProfile.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(client=self.request.user)

    def retrieve(self, request, pk=None):
        project = get_object_or_404(self.get_queryset(), pk=pk)
        serializer = self.get_serializer(project)
        return Response(serializer.data)

    def update(self, request, pk=None, *args, **kwargs):
        project = get_object_or_404(self.get_queryset(), pk=pk)
        partial = kwargs.pop('partial', False)

        serializer = self.get_serializer(project, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    def partial_update(self, request, pk=None, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, pk, *args, **kwargs)

    def destroy(self, request, pk=None, *args, **kwargs):
        project = get_object_or_404(self.get_queryset(), pk=pk)
        project.delete()
        return Response({"detail": "Project deleted successfully."}, status=status.HTTP_204_NO_CONTENT)


class SubscriptionPlanListView(generics.ListAPIView):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAuthenticated]


class CreateCheckoutSession(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreatePaymentSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data["plan"]

        checkout_session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "inr",
                    "product_data": {
                        "name": plan.name,
                    },
                    "unit_amount": int(plan.price * 100),
                },
                "quantity": 1,
            }],
            metadata={
                "payment_type": "subscription",
                "user_id": request.user.id,
                "plan_id": plan.id,
            },
            success_url="http://localhost:3000/payment-success",
            cancel_url="http://localhost:3000/payment-failed",
        )

        return Response({"checkout_url": checkout_session.url})

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_WEBHOOK_SECRET,
        )
    except Exception:
        return HttpResponse(status=400)

    if event["type"] != "checkout.session.completed":
        return HttpResponse(status=200)

    session = event["data"]["object"]
    metadata = session.get("metadata") or {}

    payment_type = metadata.get("payment_type")

    # --------------------------------------------------
    # ESCROW PAYMENT
    # --------------------------------------------------
    if payment_type == "escrow":
        offer_id = metadata.get("offer_id")
        payment_intent_id = session.get("payment_intent")

        if not offer_id or not payment_intent_id:
            return HttpResponse(status=400)

        StripeEscrowProcessor().process(
            offer_id=offer_id,
            payment_intent_id=payment_intent_id,
        )
        return HttpResponse(status=200)

    # --------------------------------------------------
    # SUBSCRIPTION PAYMENT
    # --------------------------------------------------
    if payment_type == "subscription":
        user_id = metadata.get("user_id")
        plan_id = metadata.get("plan_id")

        if not user_id or not plan_id:
            return HttpResponse(status=400)

        StripeSubscriptionProcessor().process(
            user_id=user_id,
            plan_id=plan_id,
        )
        return HttpResponse(status=200)

    return HttpResponse(status=400)

class UserSubscriptionViewSet(ListAPIView):
    serializer_class = UserSubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserSubscription.objects.filter(user=self.request.user)


class BrowseFreelancers(ListAPIView):
    serializer_class = FreelancerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return FreelancerProfile.objects.all()


class ClientProposalListView(generics.ListAPIView):
    serializer_class = ClientProposalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        latest_score = ProposalScore.objects.filter(
            proposal=OuterRef("pk"),
            is_latest=True
        )

        return (
            Proposal.objects
            .filter(project__client=user)
            .annotate(
                final_score=Coalesce(
                    Subquery(latest_score.values("final_score")[:1]),
                    0.0,
                    output_field=FloatField()
                ),
                auto_reject=Coalesce(
                    Subquery(latest_score.values("auto_reject")[:1]),
                    False,
                    output_field=BooleanField()
                ),
            )
            .order_by(
                "auto_reject",
                "-final_score",
                "-created_at"
            )
            .select_related("freelancer", "project")
        )

class ClientProposalDetailView(generics.RetrieveAPIView):
    serializer_class = ClientProposalSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"

    def get_queryset(self):
        user = self.request.user

        latest_score = ProposalScore.objects.filter(
            proposal=OuterRef("pk"),
            is_latest=True
        )

        return (
            Proposal.objects
            .filter(project__client=user)
            .annotate(
                final_score=Coalesce(
                    Subquery(latest_score.values("final_score")[:1]),
                    0.0,
                    output_field=FloatField()
                ),
                auto_reject=Coalesce(
                    Subquery(latest_score.values("auto_reject")[:1]),
                    False,
                    output_field=BooleanField()
                ),
            )
            .select_related("freelancer", "project")
        )

class ClientProposalStatusUpdateView(generics.UpdateAPIView):
    serializer_class = ProposalStatusUpdateSerializer
    permission_classes = [IsAuthenticated]
    queryset = Proposal.objects.select_related('project')

    def get_object(self):
        proposal = super().get_object()
        if proposal.project.client != self.request.user:
            raise PermissionDenied("Not allowed")
        return proposal

class FreelancerProfileDetailView(generics.RetrieveAPIView):
    serializer_class = FreelancerProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'user_id'

    def get_object(self):
        user_id = self.kwargs.get('user_id')
        try:
            profile = FreelancerProfile.objects.get(user__id=user_id)
        except FreelancerProfile.DoesNotExist:
            raise NotFound('Freelancer profile not found')

        return profile

class ClientStatisticsView(APIView):
    def get(self, request):
        user = request.user

        projects = Project.objects.filter(client=user)

        contracts = Contract.objects.filter(
            offer__proposal__project__client=user
        )

        total_spent = EscrowPayment.objects.filter(
            offer__proposal__project__client=user,
            status__in=["funded", "settled"]
        ).aggregate(
            total=Sum("amount")
        )["total"] or 0

        data = {
            "active_projects": projects.filter(
                status__in=["open", "in_progress"]
            ).count(),

            "completed_projects": projects.filter(
                status="completed"
            ).count(),

            "total_freelancers_hired": contracts.values(
                "offer__freelancer"
            ).distinct().count(),

            "total_spent": total_spent,
        }

        return Response(data)


class ClientRecentProjectsView(generics.ListAPIView):
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Project.objects.filter(client=self.request.user).order_by("-created_at")[:5]


class CompletedProjectsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = CompletedProjectSerializer

    def get_queryset(self):
        user = self.request.user

        return (
            Project.objects
            .filter(
                client=user,
                proposals__offer__contract__status="ended",
                proposals__offer__contract__end_reason="completed",
            )
            .distinct()
            .select_related("client")
            .prefetch_related(
                "proposals__offer__freelancer__user",
                "proposals__offer__contract",
            )
            .order_by("-updated_at")
        )
