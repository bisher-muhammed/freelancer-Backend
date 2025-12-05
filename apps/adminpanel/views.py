from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.permissions import IsAdminUser
from .serializers import SubscriptionPlanSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from .models import SubscriptionPlan
from rest_framework.decorators import api_view

from apps.users.serializers import AdminUserSerializer
from .serializers import AdminLoginSerializer
from apps.freelancer.models import FreelancerProfile
from apps.freelancer.serializers import FreelancerProfileSerializer

User = get_user_model()


class AdminLoginView(APIView):
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



class AdminSubscriptionPlanViewSet(viewsets.ModelViewSet):
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [permissions.IsAdminUser]



@api_view(['POST'])
def toggle_block(request):
    user_id = request.data.get("user_id")
    if not user_id:
        return Response({"error": "user_id is required"}, status=400)

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=404)

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
def admin_get_freelancer(request, user_id):
    profile = FreelancerProfile.objects.get(user__id=user_id)
    serializer = FreelancerProfileSerializer(profile)
    return Response(serializer.data)

                     

@api_view(['POST'])
def admin_verify_freelancer(request,user_id):
    profile = FreelancerProfile.objects.get(user__id=user_id)

    if profile.is_verified:
        return Response({"details":"Already verified"},status=400)
    
    profile.is_verified =True
    profile.save()

    return Response({"detail": "Freelancer verified successfully"})



