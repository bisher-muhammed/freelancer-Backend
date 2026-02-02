from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model

from apps.users.serializers import UserMiniSerializer
from .models import SubscriptionPlan, TrackingPolicy
from apps.users.models import Project
from apps.applications.models import Meeting, ProjectScoringConfig, ProposalScore
User = get_user_model()


class AdminLoginSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        if not email or not password:
            raise serializers.ValidationError("Email and password are required")

        user = authenticate(email=email, password=password)

        if not user:
            raise serializers.ValidationError("Invalid credentials")

        if not (user.role == "admin" and user.is_superuser and user.is_staff):
            raise serializers.ValidationError("Unauthorized: Not an admin user")

        data["user"] = user
        return data
    

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = "__all__"
    


class ProjectScoringConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectScoringConfig
        fields = [
            "id",
            "experience_level",
            "skill_weight",
            "experience_weight",
            "budget_weight",
            "reliability_weight",
            "min_final_score",
            "auto_reject_on_red_flags",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, data):
        # Use instance values if updating and field is missing
        instance = getattr(self, "instance", None)
        skill = data.get("skill_weight", getattr(instance, "skill_weight", 0))
        experience = data.get("experience_weight", getattr(instance, "experience_weight", 0))
        budget = data.get("budget_weight", getattr(instance, "budget_weight", 0))
        reliability = data.get("reliability_weight", getattr(instance, "reliability_weight", 0))

        # Ensure each weight is 0-1
        for w_name, w_val in [
            ("skill_weight", skill),
            ("experience_weight", experience),
            ("budget_weight", budget),
            ("reliability_weight", reliability),
        ]:
            if not 0 <= w_val <= 1:
                raise serializers.ValidationError({w_name: "Weight must be between 0 and 1."})

        total = skill + experience + budget + reliability
        if abs(total - 1.0) > 0.01:
            raise serializers.ValidationError("All weights must sum to 1.0 (100%).")

        return data


class AdminMeetingSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(
        source="chat_room.client.email",
        read_only=True
    )
    freelancer_email = serializers.EmailField(
        source="chat_room.freelancer.email",
        read_only=True
    )
    project = serializers.CharField(
        source="proposal.project.title",
        read_only=True
    )

    class Meta:
        model = Meeting
        fields = [
            "id",
            "project",
            "proposal",
            "meeting_type",
            "status",
            "actual_started_at",
            "actual_ended_at",
            "client_email",
            "freelancer_email",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
    


class AdminProjectListSerializer(serializers.ModelSerializer):
    client_email = serializers.EmailField(source="client.email", read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "status",
            "budget_type",
            "fixed_budget",
            "hourly_min_rate",
            "hourly_max_rate",
            "created_at",
            "client_email",
        ]
        read_only_fields = ["id", "created_at"]


class AdminProjectDetailSerializer(serializers.ModelSerializer):
    skills_required = serializers.StringRelatedField(many=True)
    client = UserMiniSerializer(read_only=True)

    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ["id", "created_at"]








class TrackingPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingPolicy
        fields = [
            "id",
            "version",
            "title",
            "content",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_version(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Version cannot be empty")
        return value
