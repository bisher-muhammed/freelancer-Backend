from rest_framework import viewsets, permissions, status, generics
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
import logging
import json

from apps.billing.selectors import InvoiceEarningsSelector

from .models import (
    FreelancerProfile, Category, PortfolioProject,
    Skill, FreelancerSkill, Education, EmploymentHistory
)
from .serializers import (
    FreelancerProfileSerializer, CategorySerializer,
    PortfolioProjectSerializer, SkillSerializer
)
from apps.users.serializers import ProjectSerializer
from apps.users.models import Project

logger = logging.getLogger(__name__)


# ============================================================================
# CATEGORY & SKILL VIEWSETS
# ============================================================================

class CategoryViewSet(viewsets.ModelViewSet):
    """Manage skill categories."""
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class SkillViewSet(viewsets.ModelViewSet):
    """Manage skills."""
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


# ============================================================================
# FREELANCER PROFILE VIEWSET
# ============================================================================

class FreelancerProfileViewSet(viewsets.ModelViewSet):
    """
    Manage freelancer profiles with nested skills, education, and experience.
    """
    queryset = FreelancerProfile.objects.select_related("user").prefetch_related(
    "skills__skill__categories",
    "education_set",
    "employmenthistory_set"
    )

    serializer_class = FreelancerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'post', 'patch', 'put', 'delete']

    def get_queryset(self):
        """Filter queryset based on user permissions."""
        user = self.request.user
        return self.queryset if user.is_staff else self.queryset.filter(user=user)

    def get_object(self):
        """Get or create profile for the current user."""
        if self.request.user.role != "freelancer":
            raise PermissionDenied("Only freelancers can have profiles.")

        # If no PK provided, get or create for current user
        if self.kwargs.get("pk") is None:
            obj, _ = FreelancerProfile.objects.get_or_create(user=self.request.user)
            return obj

        # Otherwise, get specific profile with permission check
        obj = get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])

        if obj.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied("You can only access your own profile.")

        return obj

    def list(self, request, *args, **kwargs):
        """Return only the current user's profile."""
        if request.user.role != "freelancer":
            raise PermissionDenied("Only freelancers can access freelancer profiles.")

        profile, _ = FreelancerProfile.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(profile)
        return Response({"count": 1, "results": [serializer.data]})

    def create(self, request, *args, **kwargs):
        """Create or update freelancer profile."""
        if FreelancerProfile.objects.filter(user=request.user).exists():
            return self.partial_update(request, *args, **kwargs)

        data = self._parse_form_data(request.data)
        serializer = self.get_serializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Full update of profile."""
        return self._perform_update(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        """Partial update of profile."""
        return self._perform_update(request, partial=True)

    def _perform_update(self, request, partial):
        """Common update logic."""
        profile = self.get_object()
        data = self._parse_form_data(request.data)
        serializer = self.get_serializer(
            profile,
            data=data,
            partial=partial,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def _parse_form_data(self, data):
        """Convert FormData JSON strings to Python objects."""
        parsed = data.copy()
        json_fields = ["skills", "categories", "education_input", "experience_input"]

        for field in json_fields:
            value = parsed.get(field)
            if isinstance(value, str):
                try:
                    parsed[field] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    pass
        return parsed

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_files(self, request, pk=None):
        """Dedicated endpoint for file uploads."""
        profile = self.get_object()

        if "profile_picture" in request.FILES:
            profile.profile_picture = request.FILES["profile_picture"]
        if "resume" in request.FILES:
            profile.resume = request.FILES["resume"]

        profile.save()
        serializer = self.get_serializer(profile)
        return Response(serializer.data)


# ============================================================================
# PORTFOLIO PROJECT VIEWSET
# ============================================================================

class PortfolioProjectViewSet(viewsets.ModelViewSet):
    """Manage portfolio projects for freelancers."""
    serializer_class = PortfolioProjectSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        """Return projects for the current user's freelancer profile."""
        return PortfolioProject.objects.filter(
            freelancer__user=self.request.user
        )

    def perform_create(self, serializer):
        """Associate project with current user's freelancer profile."""
        freelancer = FreelancerProfile.objects.get(user=self.request.user)
        serializer.save(freelancer=freelancer)


# ============================================================================
# OPEN PROJECTS LIST
# ============================================================================

class OpenProjectListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.filter(status="open").order_by("-created_at")


class FreelancerEarningsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        if not hasattr(request.user, "freelancer_profile"): 
            return Response(
                {"detail": "Only freelancers can access earnings summary"},
                status=403,
            )

        data = InvoiceEarningsSelector.freelancer_summary(
            request.user.freelancer_profile  
        )
        return Response(data)


class RelatedProjectsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        freelancer = self.request.user.freelancer_profile
        skills = freelancer.skills.values_list("skill_id", flat=True)

        return (
            Project.objects
            .filter(
                skills_required__id__in=skills,
                status="open"
            )
            .distinct()
            .order_by("-created_at")
        )




