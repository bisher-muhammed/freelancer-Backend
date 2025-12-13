from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps. users.models import Project, ClientProfile, User
from apps. freelancer.models import Skill
from .models import Proposal


# ---------------- Client Info ----------------
class ClientInfoSerializer(serializers.ModelSerializer):
    member_since = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = ClientProfile
        fields = [
            'company_name',
            'country',
            'city',
            'verified',
            'member_since',
            'profile_picture',
        ]

    def get_member_since(self, obj):
        return obj.user.created_at.strftime("%B %Y") if obj.user.created_at else None
    
    def get_profile_picture(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            # Fallback if no request in context
            return obj.profile_picture.url
        return None


# ---------------- Skill Serializer ----------------
class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ['id', 'name']


# ---------------- Project Detail ----------------
class ProjectDetailSerializer(serializers.ModelSerializer):
    skills_required = SkillSerializer(many=True, read_only=True)
    client = serializers.SerializerMethodField()
    already_applied = serializers.SerializerMethodField()
    

    class Meta:
        model = Project
        fields = [
            'id',
            'title',
            'description',
            'skills_required',
            'budget_type',
            'fixed_budget',
            'hourly_min_rate',
            'hourly_max_rate',
            'duration',
            'experience_level',
            'status',
            'created_at',
            'client',
            'already_applied',
        ]

    def get_client(self, obj):
        profile = ClientProfile.objects.filter(user=obj.client).first()
        if not profile:
            return None
        # IMPORTANT: Pass the context to the nested serializer
        return ClientInfoSerializer(profile, context=self.context).data

    def get_already_applied(self, obj):
        user = self.context.get('request').user
        if user.is_authenticated:
            return obj.proposals.filter(freelancer=user).exists()
        return False

# ---------------- Proposal Create / Apply ----------------
from rest_framework import serializers
from .models import Proposal

class ProposalCreateSerializer(serializers.ModelSerializer):
    freelancer = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = Proposal
        fields = [
            'project',
            'freelancer',
            'cover_letter',
            'bid_fixed_price',
            'bid_hourly_rate',
        ]

    def validate_cover_letter(self, value):
        """
        Ensure cover letter is not too short or too long, and optionally check for formatting.
        """
        if not value.strip():
            raise serializers.ValidationError("Cover letter cannot be empty.")
        if len(value) < 100:
            raise serializers.ValidationError("Cover letter must be at least 100 characters.")
        if len(value) > 2000:
            raise serializers.ValidationError("Cover letter cannot exceed 2000 characters.")

        # Optional: simple format validation (e.g., no scripts)
        if "<script>" in value.lower():
            raise serializers.ValidationError("Invalid content in cover letter.")

        return value

    def validate(self, attrs):
        request = self.context['request']
        user = request.user
        project = attrs.get('project')

        # Prevent applying to own project
        if project.client == user:
            raise serializers.ValidationError("You cannot apply to your own project.")

        # Prevent duplicate application
        if Proposal.objects.filter(project=project, freelancer=user).exists():
            raise serializers.ValidationError("You have already applied to this project.")

        # Project must be open
        if project.status != 'open':
            raise serializers.ValidationError("This project is not open for applications.")

        # Validate bid fields depending on project type
        if project.budget_type == 'fixed':
            if not attrs.get('bid_fixed_price'):
                raise serializers.ValidationError("Bid amount is required for fixed projects.")
            if attrs.get('bid_hourly_rate'):
                raise serializers.ValidationError("Hourly bid not allowed for fixed projects.")
        elif project.budget_type == 'hourly':
            if not attrs.get('bid_hourly_rate'):
                raise serializers.ValidationError("Hourly bid rate is required for hourly projects.")
            if attrs.get('bid_fixed_price'):
                raise serializers.ValidationError("Fixed bid not allowed for hourly projects.")

        return attrs



class MyProposalSerializer(serializers.ModelSerializer):
    project = ProjectDetailSerializer(read_only=True)

    class Meta:
        model = Proposal
        fields = [
            'id',
            'status',
            'cover_letter',
            'bid_fixed_price',
            'bid_hourly_rate',
            'created_at',
            'project',
        ]
