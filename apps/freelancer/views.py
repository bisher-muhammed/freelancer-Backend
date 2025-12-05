from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.decorators import api_view, permission_classes, parser_classes, action
from rest_framework.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404
import logging
import json
from rest_framework import generics

from .models import FreelancerProfile, Category, Skill, FreelancerSkill, Education, EmploymentHistory
from .serializers import FreelancerProfileSerializer, CategorySerializer, SkillSerializer
from .utils import process_freelancer_document
from apps.users.serializers import ProjectSerializer
from apps.users.models import Project
logger = logging.getLogger(__name__)


# ---------------------------
# Skill / Category ViewSets
# ---------------------------
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class SkillViewSet(viewsets.ModelViewSet):
    queryset = Skill.objects.all()
    serializer_class = SkillSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


# ---------------------------
# Freelancer Profile ViewSet
# ---------------------------
class FreelancerProfileViewSet(viewsets.ModelViewSet):
    queryset = FreelancerProfile.objects.select_related("user").prefetch_related(
        "freelancerskill_set__skill__category",
        "education_set",
        "employmenthistory_set"
    )
    serializer_class = FreelancerProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    http_method_names = ['get', 'post', 'patch', 'put', 'delete']

    # ------------------------------------
    # Query Restriction
    # ------------------------------------
    def get_queryset(self):
        user = self.request.user
        return self.queryset if user.is_staff else self.queryset.filter(user=user)

    # ------------------------------------
    # Object Restriction
    # ------------------------------------
    def get_object(self):
        if self.request.user.role != "freelancer":
            raise PermissionDenied("Only freelancers can have profiles.")

        if self.kwargs.get("pk") is None:
            obj, _ = FreelancerProfile.objects.get_or_create(user=self.request.user)
            return obj

        obj = get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])

        if obj.user != self.request.user and not self.request.user.is_staff:
            raise PermissionDenied("You can only access your own profile.")

        return obj
    


    # ------------------------------------
    # List → Always return the current user's profile only
    # ------------------------------------
    def list(self, request, *args, **kwargs):
        if request.user.role != "freelancer":
            raise PermissionDenied("Only freelancers can access freelancer profiles.")

        profile, _ = FreelancerProfile.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(profile)
        return Response({"count": 1, "results": [serializer.data]})
    


    # ------------------------------------
    # Create
    # ------------------------------------
    def create(self, request, *args, **kwargs):
        # If profile already exists → treat as update
        if FreelancerProfile.objects.filter(user=request.user).exists():
            return self.partial_update(request, *args, **kwargs)

        data = self._parse_form_data(request.data)

        serializer = self.get_serializer(data=data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ------------------------------------
    # Update (PUT/PATCH)
    # ------------------------------------
    def update(self, request, *args, **kwargs):
        return self._update_common(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_common(request, partial=True)

    def _update_common(self, request, partial):
        profile = self.get_object()

        # Convert JSON strings → objects
        data = self._parse_form_data(request.data)

        # Log the parsed data for debugging
        logger.info(f"Parsed data: {data}")

        # Pass everything; serializer handles file fields correctly
        serializer = self.get_serializer(
            profile,
            data=data,
            partial=partial,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)

    # ------------------------------------
    # Convert FormData "JSON strings" to actual Python objects
    # ------------------------------------
    def _parse_form_data(self, data):
        """
        Parse JSON string fields from FormData into Python objects.
        This handles the case where frontend sends JSON.stringify() data.
        """
        parsed = data.copy()

        json_fields = ["skills", "categories", "education_input", "experience_input"]

        for field in json_fields:
            value = parsed.get(field)
            # Only parse if it's a string (meaning it came as JSON from FormData)
            if isinstance(value, str):
                try:
                    parsed_value = json.loads(value)
                    parsed[field] = parsed_value
                    logger.info(f"Successfully parsed {field}: {type(parsed_value)}")
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"Failed to parse JSON for field '{field}': {e}")
                    # Leave as is if parsing fails
            # If it's already a list/dict (from JSON request), leave it as is
            elif isinstance(value, (list, dict)):
                logger.info(f"Field {field} is already parsed: {type(value)}")
                pass

        return parsed

    # ------------------------------------
    # Dedicated file upload endpoint (rarely needed)
    # ------------------------------------
    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def upload_files(self, request, pk=None):
        profile = self.get_object()

        if "profile_picture" in request.FILES:
            profile.profile_picture = request.FILES["profile_picture"]

        if "resume" in request.FILES:
            profile.resume = request.FILES["resume"]

        profile.save()

        serializer = self.get_serializer(profile)
        return Response(serializer.data)



# ---------------------------
# Upload Resume + AI Extraction
# ---------------------------
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def upload_resume(request):
    """
    Upload resume and/or profile picture, extract data using AI
    Returns extracted data for user confirmation (does not auto-save)
    """
    user = request.user
    profile, _ = FreelancerProfile.objects.get_or_create(user=user)

    resume_file = request.FILES.get("resume")
    profile_pic = request.FILES.get("profile_picture")

    if not resume_file and not profile_pic:
        return Response(
            {"error": "No file provided."}, 
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        with transaction.atomic():
            # Save files first
            if resume_file:
                profile.resume = resume_file
            if profile_pic:
                profile.profile_picture = profile_pic
            profile.save()

            # Extract data from resume if provided
            extracted_data = {}
            if resume_file:
                # Get file path
                file_path = profile.resume.path if hasattr(profile.resume, 'path') else None
                
                if file_path:
                    # Process resume and get extracted data
                    ai_response = process_freelancer_document(file_path)
                    
                    # Format the response for frontend
                    extracted_data = {
                        "title": ai_response.get("positions", [""])[0] if ai_response.get("positions") else "",
                        "bio": ai_response.get("bio", ""),
                        "contact_number": "",  # Not extracted from resume
                        "hourly_rate": "",  # Not extracted from resume
                        "skills": [skill["name"] for skill in ai_response.get("skills", [])],
                        "categories": list(set([
                            skill.get("category") 
                            for skill in ai_response.get("skills", []) 
                            if skill.get("category")
                        ])) or ["General"],
                        "education": ai_response.get("education", []),
                        "experience": ai_response.get("experience", []),
                    }

            # Get updated profile data
            profile.refresh_from_db()
            serializer = FreelancerProfileSerializer(profile, context={'request': request})

            return Response({
                "message": "Files uploaded successfully. Review the extracted data.",
                "profile": serializer.data,
                "extracted_data": extracted_data if extracted_data else None,
            }, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Failed to process files: {str(e)}")
        import traceback
        traceback.print_exc()
        return Response(
            {"error": f"Failed to process files: {str(e)}"}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


class OpenProjectListView(generics.ListAPIView):
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return  Project.objects.filter(status="open").order_by("-created_at")
    