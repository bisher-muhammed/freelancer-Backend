from rest_framework import status, generics
from rest_framework.response import Response
from rest_framework.permissions import AllowAny,IsAuthenticated
from rest_framework.views import APIView

from apps.applications.services.create_contract import create_contract_for_offer
from apps.notifications.services import create_notifications
from .models import ClientProfile,Project, UserSubscription
from rest_framework.exceptions import NotFound
from django.contrib.auth import get_user_model
from rest_framework import viewsets
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from apps.adminpanel.models import SubscriptionPlan
from rest_framework import permissions
from apps.adminpanel.serializers import SubscriptionPlanSerializer
from django.utils import timezone
import stripe
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from django.db import transaction
from rest_framework.generics import ListAPIView
from .serializers import CreatePaymentSerializer, UserSubscriptionSerializer
from apps.freelancer.models import FreelancerProfile
from apps. freelancer.serializers import FreelancerProfileSerializer
from apps.applications.models import EscrowPayment, Offer, Proposal, ProposalScore
from django.db.models import OuterRef, Subquery, FloatField, BooleanField
from django.db.models.functions import Coalesce
from .serializers import (
    ProjectSerializer,
    SendOTPSerializer,
    RegisterFormSerializer,
    VerifyOTPSerializer,
    LoginSerializer,
    ForgotPasswordSerializer
    ,VerifyPasswordResetOTPSerializer
    ,ResetPasswordSerializer,
    ClientProfileSerializer,
    ClientProposalSerializer,
    ProposalStatusUpdateSerializer
    

    
)



User = get_user_model()
stripe.api_key = settings.STRIPE_SECRET_KEY
 

# -------- 1️⃣ Send / Resend OTP --------
class SendOTPView(generics.GenericAPIView):
    """
    Accepts user's email and sends (or resends) an OTP.
    Used for both initial send and resend during registration.
    """
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


# -------- 2️⃣ Register Form Submission --------
class RegisterView(generics.GenericAPIView):
    """
    Step 2: Accept registration form (email, username, password, etc.)
    - Validates but DOES NOT create the user.
    - Just ensures data is valid and expects OTP verification next.
    """
    serializer_class = RegisterFormSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            # No OTP sent here; user already received via SendOTPView
            return Response(
                {
                    "success": True,
                    "message": "Form submitted successfully. Please verify OTP to complete registration.",
                    "data": serializer.validated_data,
                },
                status=status.HTTP_200_OK,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# -------- 3️⃣ Verify OTP and Create User --------
class VerifyOTPView(generics.GenericAPIView):
    """
    Step 3: Verify OTP and create the user account.
    - Validates OTP via verify_otp().
    - Creates and returns the user upon success.
    """
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
    """
    Login using email and password.
    Returns access and refresh JWT tokens.
    """
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
    


#define views for password reset below
# ---------- 1️⃣ Forgot Password ----------
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


# ---------- 2️⃣ Verify OTP ----------
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


# ---------- 3️⃣ Reset Password ----------
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


#----- User Profile view CrUD operations can be added below -----#

from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from .models import ClientProfile
from .serializers import ClientProfileSerializer

from rest_framework.decorators import action
from rest_framework.response import Response

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










from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.conf import settings
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


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
        
        
        # ✅ Verify token with Google
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )
        
        # Validate issuer
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
        import traceback
        print("📜 Full traceback:")
        traceback.print_exc()
        return Response({
            "success": False,
            "message": "Token verification failed",
            "error": str(e)
        }, status=400)

    # Check if user exists
    
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({
            "success": False,
            "message": "Email not registered. Please register using password first."
        }, status=404)

    # Generate JWT tokens
    try:
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)
        
        print(f"✅ Access token generated (length: {len(access_token)})")
        print(f"✅ Refresh token generated (length: {len(refresh_token)})")
        
    except Exception as e:
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



from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Project
from .serializers import ProjectSerializer

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
        serializer = CreatePaymentSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        plan = serializer.validated_data["plan"]

        amount = int(plan.price * 100)

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='payment',
            line_items=[{
                "price_data": {
                    "currency": "inr",
                    "product_data": {"name": plan.name},
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            metadata={
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
    endpoint_secret = settings.STRIPE_WEBHOOK_SECRET

    # -----------------------------------
    # 1. Verify Stripe Signature
    # -----------------------------------
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception:
        return HttpResponse(status=400)

    # -----------------------------------
    # 2. Only Handle Checkout Success
    # -----------------------------------
    if event["type"] != "checkout.session.completed":
        return HttpResponse(status=200)

    session = event["data"]["object"]

    metadata = session.get("metadata", {})
    payment_type = metadata.get("payment_type")
    payment_intent_id = session.get("payment_intent")

    if not payment_type or not payment_intent_id:
        return HttpResponse(status=400)

    # ==========================================================
    # ✅ CASE 1: ESCROW PAYMENT (Offer Contract Funding)
    # ==========================================================
    if payment_type == "escrow":

        offer_id = metadata.get("offer_id")
        if not offer_id:
            return HttpResponse(status=400)

        with transaction.atomic():
            try:
                offer = Offer.objects.select_for_update().get(id=offer_id)
                payment = offer.payment
            except Offer.DoesNotExist:
                return HttpResponse(status=404)
            except EscrowPayment.DoesNotExist:
                return HttpResponse(status=404)

            # ✅ Idempotency Guard
            if payment.status == "escrowed":
                return HttpResponse(status=200)

            if payment.stripe_payment_intent_id == payment_intent_id:
                return HttpResponse(status=200)

            if payment.status != "pending":
                return HttpResponse(status=200)

            # ✅ Mark Escrowed
            payment.status = "escrowed"
            payment.escrowed_at = timezone.now()
            payment.stripe_payment_intent_id = payment_intent_id
            payment.save()

            freelancer_user = offer.proposal.freelancer
            client_user = offer.client
            project = offer.proposal.project

            # ✅ Notify Freelancer: Escrow Funded
            create_notifications.notify_user(
                recipient=freelancer_user,
                notif_type="ESCROW_FUNDED",
                title="Escrow Funded 💰",
                message=f"Client funded escrow for '{project.title}'.",
                data={"offer_id": offer.id}
            )

            # ✅ Create Contract
            contract = create_contract_for_offer(offer)

            # ✅ Notify Both: Contract Started
            create_notifications.notify_user(
                recipient=freelancer_user,
                notif_type="CONTRACT_STARTED",
                title="Contract Started ✅",
                message=f"Contract is now active for '{project.title}'.",
                data={"contract_id": contract.id}
            )

            create_notifications.notify_user(
                recipient=client_user,
                notif_type="CONTRACT_STARTED",
                title="Contract Started ✅",
                message=f"You successfully hired {freelancer_user.username}.",
                data={"contract_id": contract.id}
            )

        return HttpResponse(status=200)

    # ==========================================================
    # ✅ CASE 2: SUBSCRIPTION PAYMENT (Plan Purchase)
    # ==========================================================
    elif payment_type == "subscription":

        subscription_id = metadata.get("subscription_id")
        if not subscription_id:
            return HttpResponse(status=400)

        with transaction.atomic():
            try:
                subscription = UserSubscription.objects.select_for_update().get(
                    id=subscription_id
                )
            except UserSubscription.DoesNotExist:
                return HttpResponse(status=404)

            # ✅ Idempotency Guard
            if subscription.status == "active":
                return HttpResponse(status=200)

            # ✅ Activate Subscription
            subscription.status = "active"
            subscription.activated_at = timezone.now()
            subscription.stripe_payment_intent_id = payment_intent_id
            subscription.save()

            client_user = subscription.user

            # ✅ Notify Client: Subscription Activated
            create_notifications.notify_user(
                recipient=client_user,
                notif_type="SUBSCRIPTION_ACTIVE",
                title="Plan Activated 🎉",
                message="Your subscription payment was successful. You can now post new projects.",
                data={"subscription_id": subscription.id}
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
            # 🔥 PRIORITY ORDERING
            .order_by(
                "auto_reject",        # False first
                "-final_score",       # High → Low
                "-created_at"         # Newer as tiebreaker
            )
            .select_related("freelancer", "project")
        )


class ClientProposalDetailView(generics.RetrieveAPIView):
    serializer_class = ClientProposalSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "pk"  # default, can use 'id'

    def get_queryset(self):
        user = self.request.user

        latest_score = ProposalScore.objects.filter(
            proposal=OuterRef("pk"),
            is_latest=True
        )

        return (
            Proposal.objects
            .filter(project__client=user)  # Only proposals for this client
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
        proposal = super().get_object()  # This is a single object now
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
            raise NotFound('freelancerprofile not found')
        
        return profile
    