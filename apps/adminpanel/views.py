from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework import viewsets, generics
from rest_framework.permissions import IsAdminUser
from django.db.models import ProtectedError, Sum
from datetime import timedelta
from django.utils.timezone import now

from apps.applications.serializers import MeetingSerializer
from apps.contract.models import Contract
from apps.finance.models import LedgerEntry
from apps.users.models import Project
from .serializers import AdminMeetingSerializer, AdminMeetingSerializer, AdminProjectDetailSerializer, AdminProjectListSerializer, AdminProjectListSerializer, SubscriptionPlanSerializer, TrackingPolicySerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import SubscriptionPlan, TrackingPolicy
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from apps.users.serializers import AdminUserSerializer
from .serializers import AdminLoginSerializer
from apps.freelancer.models import FreelancerProfile
from apps.freelancer.serializers import FreelancerProfileSerializer
from apps.applications.models import Meeting, ProposalScore
from .serializers import ProjectScoringConfigSerializer
from apps.applications.models import ProjectScoringConfig
User = get_user_model()


class AdminLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = AdminLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "message": "Admin login successful",
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "role": user.role,
                },
                "access": str(refresh.access_token),
                "refresh": str(refresh),
            },
            status=status.HTTP_200_OK,
        )


class AdminUserList(ListAPIView):
    serializer_class = AdminUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["role", "is_active"]
    search_fields = ["email", "username"]
    ordering_fields = ["date_joined", "id", "username"]

    def get_queryset(self):
        """Return only if the requesting user is an admin."""
        current_user = self.request.user

        if current_user.role != "admin":
            # No need for custom responses. Let DRF handle forbidden.
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only admin can view users")

        return User.objects.all().order_by("-date_joined")



def _destroy_unless_protected(instance, protected_message):
    try:
        instance.delete()
    except ProtectedError:
        return Response({"detail": protected_message}, status=status.HTTP_400_BAD_REQUEST)
    return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserDetailView(generics.RetrieveDestroyAPIView):
    """Admin view / delete of a single user (used by the admin UI)."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "You cannot delete your own account."}, status=400)
        if user.is_superuser:
            return Response({"detail": "Superusers cannot be deleted here."}, status=400)
        # Users with contracts / billing / payout history are PROTECTed by
        # those records; block them instead of deleting financial history.
        return _destroy_unless_protected(
            user,
            "This user has contract or payment history and cannot be deleted. Block the account instead.",
        )


class AdminSubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAdminUser]



@api_view(['POST'])
@permission_classes([IsAdminUser])
def toggle_block(request):
    user_id = request.data.get("user_id")
    if not user_id:
        return Response({"error": "user_id is required"}, status=400)

    try:
        user = User.objects.get(id=user_id)
    except (User.DoesNotExist, ValueError, TypeError):
        return Response({"error": "User not found"}, status=404)

    if user.pk == request.user.pk:
        return Response({"error": "You cannot block your own account"}, status=400)

    # Flip the current state
    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])

    status_text = "unblocked" if user.is_active else "blocked"

    return Response({
        "message": f"User {status_text} successfully",
        "user_id": user.id,
        "is_active": user.is_active
    })



@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_get_freelancer(request, user_id):
    profile = get_object_or_404(FreelancerProfile, user__id=user_id)
    serializer = FreelancerProfileSerializer(profile, context={"request": request})
    return Response(serializer.data)



@api_view(['POST'])
@permission_classes([IsAdminUser])
def admin_verify_freelancer(request,user_id):
    profile = get_object_or_404(FreelancerProfile, user__id=user_id)

    if profile.is_verified:
        return Response({"details":"Already verified"},status=400)
    
    profile.is_verified =True
    profile.save()

    return Response({"detail": "Freelancer verified successfully"})



class AdminProjectScoringConfigViewSet(viewsets.ModelViewSet):
    """
    Admin defines global scoring rules per experience level.
    Used by the system to auto-score proposals.
    """
    serializer_class = ProjectScoringConfigSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = ProjectScoringConfig.objects.all()
        level = self.request.query_params.get("experience_level")
        if level:
            queryset = queryset.filter(experience_level=level)
        return queryset

    def perform_create(self, serializer):
        level = serializer.validated_data["experience_level"]

        if ProjectScoringConfig.objects.filter(experience_level=level).exists():
            raise ValidationError(f"Scoring configuration already exists for {level} level.")

        # ProjectScoringConfig.save() already runs full_clean()
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()



class AdminMeetingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin can view ALL meetings across the platform.
    No creation, no participant restriction.
    """

    queryset = (
        Meeting.objects
        .select_related(
            "proposal",
            "chat_room",
            "chat_room__client",
            "chat_room__freelancer",
            "proposal__project",
        )
        .order_by("-created_at")
    )

    serializer_class = AdminMeetingSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]

    filterset_fields = [
        "status",
        "meeting_type",
        "proposal__project",
    ]

    search_fields = [
        "proposal__project__title",
        "chat_room__client__email",
        "chat_room__freelancer__email",
    ]

    ordering_fields = [
        "start_time",
        "created_at",
        "status",
    ]




class AdminProjectListView(generics.ListAPIView):
    serializer_class = AdminProjectListSerializer
    permission_classes = [IsAdminUser]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "budget_type"]
    search_fields = ["title", "client__email"]
    ordering_fields = ["created_at", "fixed_budget", "hourly_min_rate"]
    ordering = ["-created_at"]

    def get_queryset(self):
        return (
            Project.objects
            .select_related("client")
            .prefetch_related("skills_required")
        )

class AdminProjectDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = AdminProjectDetailSerializer
    permission_classes = [IsAdminUser]

    def destroy(self, request, *args, **kwargs):
        return _destroy_unless_protected(
            self.get_object(),
            "This project has a contract and cannot be deleted.",
        )

    def get_queryset(self):
        return (
            Project.objects
            .select_related("client")
            .prefetch_related("skills_required")
        )



class TrackingPolicyCreateView(generics.CreateAPIView):
    serializer_class = TrackingPolicySerializer
    permission_classes = [IsAdminUser]


class TrackingPolicyListView(generics.ListAPIView):
    serializer_class = TrackingPolicySerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        return TrackingPolicy.objects.all().order_by("-created_at")


class TrackingPolicyUpdateView(generics.UpdateAPIView):
    serializer_class = TrackingPolicySerializer
    permission_classes = [IsAdminUser]
    queryset = TrackingPolicy.objects.all()


class TrackingPolicyDeleteView(generics.DestroyAPIView):
    permission_classes = [IsAdminUser]
    queryset = TrackingPolicy.objects.all()

    def destroy(self, request, *args, **kwargs):
        policy = self.get_object()
        try:
            policy.delete()
        except ProtectedError:
            # Contracts reference accepted policies (on_delete=PROTECT)
            return Response(
                {"detail": "This policy has been accepted on contracts. Deactivate it instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)




User = get_user_model()


class AdminFinanceStatsView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        now_dt = now()
        start_this_month = now_dt.replace(day=1)
        start_last_month = (start_this_month - timedelta(days=1)).replace(day=1)

        def pct(curr, prev):
            if prev == 0:
                return None
            return round(((curr - prev) / prev) * 100, 2)

        total_users = User.objects.count()
        users_this = User.objects.filter(
            date_joined__gte=start_this_month
        ).count()
        users_last = User.objects.filter(
            date_joined__gte=start_last_month,
            date_joined__lt=start_this_month,
        ).count()

        active_projects = (
            Contract.objects
            .filter(status="active")
            .values("offer__proposal__project")
            .distinct()
            .count()
        )

        revenue_this = (
            LedgerEntry.objects
            .filter(
                entry_type__in=["subscription", "platform_fee"],
                created_at__gte=start_this_month,
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        revenue_last = (
            LedgerEntry.objects
            .filter(
                entry_type__in=["subscription", "platform_fee"],
                created_at__gte=start_last_month,
                created_at__lt=start_this_month,
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        platform_fee_this = (
            LedgerEntry.objects
            .filter(
                entry_type="platform_fee",
                created_at__gte=start_this_month,
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        platform_fee_last = (
            LedgerEntry.objects
            .filter(
                entry_type="platform_fee",
                created_at__gte=start_last_month,
                created_at__lt=start_this_month,
            )
            .aggregate(total=Sum("amount"))["total"] or 0
        )

        return Response({
            "total_users": {
                "value": total_users,
                "change_pct": pct(users_this, users_last),
            },
            "active_projects": active_projects,
            "total_revenue": {
                "value": revenue_this,
                "change_pct": pct(revenue_this, revenue_last),
            },
            "platform_fee": {
                "value": platform_fee_this,
                "change_pct": pct(platform_fee_this, platform_fee_last),
            },
        })

