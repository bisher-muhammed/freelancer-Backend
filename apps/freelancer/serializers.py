from rest_framework import serializers
from django.db import transaction
import logging
import json

from .models import (
    Category, Skill, FreelancerProfile, FreelancerSkill,
    PortfolioProject, EmploymentHistory, Education, Pricing
)

logger = logging.getLogger(__name__)


# ============================================================================
# UTILITY FIELDS
# ============================================================================

class FlexibleJSONField(serializers.Field):
    """
    Accepts JSON strings, Python lists/dicts, or comma-separated strings.
    Normalizes all inputs to Python objects (list/dict).
    """
    def to_internal_value(self, data):
        if isinstance(data, (list, dict)):
            return data
        
        if isinstance(data, str):
            try:
                return json.loads(data)
            except (json.JSONDecodeError, ValueError):
                if ',' in data:
                    return [item.strip() for item in data.split(',') if item.strip()]
                return [data.strip()] if data.strip() else []
        
        return [] if data in (None, '') else list(data)
    
    def to_representation(self, value):
        return value


# ============================================================================
# BASE SERIALIZERS
# ============================================================================

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class SkillSerializer(serializers.ModelSerializer):
    categories = CategorySerializer(many=True, read_only=True)

    class Meta:
        model = Skill
        fields = ["id", "name", "categories"]


class FreelancerSkillSerializer(serializers.ModelSerializer):
    skill = SkillSerializer(read_only=True)
    skill_id = serializers.PrimaryKeyRelatedField(
        queryset=Skill.objects.all(),
        source='skill',
        write_only=True
    )

    class Meta:
        model = FreelancerSkill
        fields = ['id', 'skill', 'skill_id', 'level']
        read_only_fields = ['id']


class PortfolioProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioProject
        fields = ['id', 'title', 'description', 'link', 'created_at']
        read_only_fields = ['id', 'created_at']


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = ['id', 'institution', 'degree', 'year_completed']
        read_only_fields = ['id']

    def validate_year_completed(self, value):
        if not (1950 <= value <= 2100):
            raise serializers.ValidationError("Year must be between 1950 and 2100.")
        return value


class EmploymentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EmploymentHistory
        fields = ['id', 'company', 'role', 'start_date', 'end_date']
        read_only_fields = ['id']

    def validate(self, data):
        if data.get('end_date') and data.get('start_date'):
            if data['end_date'] < data['start_date']:
                raise serializers.ValidationError(
                    "End date cannot be before start date."
                )
        return data


class PricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pricing
        fields = [
            'id', 'pricing_type', 'hourly_rate',
            'min_hourly_rate', 'max_hourly_rate', 'is_default'
        ]
        read_only_fields = ['id']

    def validate(self, attrs):
        pricing_type = attrs.get('pricing_type', getattr(self.instance, 'pricing_type', None))
        hourly_rate = attrs.get('hourly_rate', getattr(self.instance, 'hourly_rate', None))
        min_rate = attrs.get('min_hourly_rate', getattr(self.instance, 'min_hourly_rate', None))
        max_rate = attrs.get('max_hourly_rate', getattr(self.instance, 'max_hourly_rate', None))

        if pricing_type == 'hourly':
            if hourly_rate is None:
                raise serializers.ValidationError({
                    'hourly_rate': 'Hourly rate is required for hourly pricing.'
                })
            attrs['min_hourly_rate'] = None
            attrs['max_hourly_rate'] = None

        elif pricing_type == 'range':
            if min_rate is None or max_rate is None:
                raise serializers.ValidationError(
                    'Both min_hourly_rate and max_hourly_rate are required for range pricing.'
                )
            if min_rate >= max_rate:
                raise serializers.ValidationError(
                    'min_hourly_rate must be less than max_hourly_rate.'
                )
            attrs['hourly_rate'] = None
        else:
            raise serializers.ValidationError('Invalid pricing_type.')

        return attrs


# ============================================================================
# FREELANCER PROFILE SERIALIZER
# ============================================================================

class FreelancerProfileSerializer(serializers.ModelSerializer):
    # Read-only user fields
    user = serializers.StringRelatedField(read_only=True)
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)

    # Computed fields (read-only)
    skills_read = serializers.SerializerMethodField()
    education = serializers.SerializerMethodField()
    experience = serializers.SerializerMethodField()
    portfolio = serializers.SerializerMethodField()
    pricing = serializers.SerializerMethodField()
    skills_names = serializers.SerializerMethodField()
    categories_names = serializers.SerializerMethodField()

    # Write-only nested data inputs
    skills = FlexibleJSONField(write_only=True, required=False)
    categories = FlexibleJSONField(write_only=True, required=False)
    education_input = FlexibleJSONField(write_only=True, required=False)
    experience_input = FlexibleJSONField(write_only=True, required=False)
    portfolio_input = FlexibleJSONField(write_only=True, required=False)
    pricing_input = FlexibleJSONField(write_only=True, required=False)

    # File fields
    resume = serializers.FileField(required=False, allow_null=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)

    # Optional fields
    contact_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )

    class Meta:
        model = FreelancerProfile
        fields = [
            
            "id", "user", "user_id", "username", "email",
            
            
            "title", "bio", "contact_number", "hourly_rate",
            "is_verified", "total_reviews", "average_rating",
            
            
            "resume", "profile_picture",
            
            # Timestamps
            "created_at", "updated_at",
            
            # Skills & categories
            "skills", "skills_read", "skills_names",
            "categories", "categories_names",
            
            # Education & experience
            "education", "education_input",
            "experience", "experience_input",
            
            # Portfolio
            "portfolio", "portfolio_input",
            
            # Pricing
            "pricing", "pricing_input",
        ]
        read_only_fields = [
            "id", "user", "user_id", "username", "email",
            "is_verified", "total_reviews", "average_rating",
            "created_at", "updated_at",
        ]

    
    
    def get_skills_read(self, obj):
        """Return full skill objects with category info."""
        return FreelancerSkillSerializer(
            obj.skills.select_related("skill").prefetch_related("skill__categories"),
            many=True
        ).data

    def get_education(self, obj):
        """Return all education entries."""
        return EducationSerializer(obj.education_set.all(), many=True).data

    def get_experience(self, obj):
        """Return all employment history entries."""
        return EmploymentHistorySerializer(
            obj.employmenthistory_set.all(),
            many=True
        ).data

    def get_portfolio(self, obj):
        """Return all portfolio projects."""
        return PortfolioProjectSerializer(
            obj.portfolioproject_set.all(),
            many=True
        ).data

    def get_pricing(self, obj):
        """Return all pricing entries."""
        return PricingSerializer(
            obj.pricing.all(),
            many=True
        ).data

    def get_skills_names(self, obj):
        """Return flat list of skill names."""
        return list(
            obj.skills
            .select_related("skill")
            .values_list("skill__name", flat=True)
        )

    def get_categories_names(self, obj):
        """Return unique list of category names from all skills."""
        categories = set()
        for freelancer_skill in obj.skills.select_related("skill").prefetch_related("skill__categories"):
            for category in freelancer_skill.skill.categories.all():
                categories.add(category.name)
        return list(categories)

    # ------------------------------------------------------------------------
    # Create & Update
    # ------------------------------------------------------------------------
    
    @transaction.atomic
    def create(self, validated_data):
        """Create a new freelancer profile with nested relations."""
        user = self.context["request"].user

        # Extract nested data
        skills = validated_data.pop("skills", [])
        categories = validated_data.pop("categories", [])
        education_list = validated_data.pop("education_input", [])
        experience_list = validated_data.pop("experience_input", [])
        portfolio_list = validated_data.pop("portfolio_input", [])
        pricing_list = validated_data.pop("pricing_input", [])
        profile_picture = validated_data.pop("profile_picture", None)
        resume = validated_data.pop("resume", None)

        # Create profile
        profile = FreelancerProfile.objects.create(user=user, **validated_data)

        # Attach files
        if profile_picture:
            profile.profile_picture = profile_picture
        if resume:
            profile.resume = resume
        profile.save()

        # Create nested relations
        self._save_skills(profile, skills, categories)
        self._save_education(profile, education_list)
        self._save_experience(profile, experience_list)
        self._save_portfolio(profile, portfolio_list)
        self._save_pricing(profile, pricing_list)

        return profile

    @transaction.atomic
    def update(self, instance, validated_data):
        """Update existing profile and optionally refresh nested relations."""
        # Extract nested data
        skills = validated_data.pop("skills", None)
        categories = validated_data.pop("categories", None)
        education_list = validated_data.pop("education_input", None)
        experience_list = validated_data.pop("experience_input", None)
        portfolio_list = validated_data.pop("portfolio_input", None)
        pricing_list = validated_data.pop("pricing_input", None)
        profile_picture = validated_data.pop("profile_picture", serializers.empty)
        resume = validated_data.pop("resume", serializers.empty)

        # Update scalar fields
        for key, value in validated_data.items():
            setattr(instance, key, value)

        # Handle file updates
        if profile_picture is not serializers.empty:
            instance.profile_picture = profile_picture or None
        if resume is not serializers.empty:
            instance.resume = resume or None

        instance.save()

        # Update nested relations if provided
        if skills is not None:
            self._save_skills(instance, skills, categories or [])
        if education_list is not None:
            self._save_education(instance, education_list)
        if experience_list is not None:
            self._save_experience(instance, experience_list)
        if portfolio_list is not None:
            self._save_portfolio(instance, portfolio_list)
        if pricing_list is not None:
            self._save_pricing(instance, pricing_list)

        return instance

    # ------------------------------------------------------------------------
    # Helper methods for nested data
    # ------------------------------------------------------------------------
    
    def _save_skills(self, profile, skills, categories):
        """Replace all skills for the profile."""
        if not isinstance(skills, (list, tuple)):
            skills = []
        if not isinstance(categories, (list, tuple)):
            categories = []

        profile.skills.all().delete()

        for index, skill_name in enumerate(skills):
            skill_name = str(skill_name).strip() if skill_name else ""
            if not skill_name:
                continue

            # Determine category
            category_names = []
            if index < len(categories) and categories[index]:
                cat_input = categories[index]
                # Handle both single category and list of categories
                if isinstance(cat_input, list):
                    category_names = [str(c).strip() for c in cat_input if c]
                else:
                    category_names = [str(cat_input).strip()]

            # Default to "General" if no categories provided
            if not category_names:
                category_names = ["General"]

            # Get or create skill
            skill_obj, _ = Skill.objects.get_or_create(name=skill_name)

            # Associate categories with the skill
            for category_name in category_names:
                category, _ = Category.objects.get_or_create(name=category_name)
                skill_obj.categories.add(category)

            # Create freelancer-skill relation
            FreelancerSkill.objects.create(
                freelancer=profile,
                skill=skill_obj,
                level=3  # Default level
            )

    def _save_education(self, profile, education_list):
        """Replace all education entries for the profile."""
        profile.education_set.all().delete()

        if not isinstance(education_list, (list, tuple)):
            return

        for edu in education_list:
            if not isinstance(edu, dict):
                continue

            institution = edu.get("institution")
            degree = edu.get("degree")
            year_completed = edu.get("year_completed") or edu.get("year")

            if not all([institution, degree, year_completed]):
                continue

            try:
                Education.objects.create(
                    freelancer=profile,
                    institution=str(institution),
                    degree=str(degree),
                    year_completed=int(year_completed)
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to create education entry: {e}")

    def _save_experience(self, profile, experience_list):
        """Replace all experience entries for the profile."""
        profile.employmenthistory_set.all().delete()

        if not isinstance(experience_list, (list, tuple)):
            return

        for exp in experience_list:
            if not isinstance(exp, dict):
                continue

            company = exp.get("company")
            role = exp.get("role")
            start_date = exp.get("start_date")

            if not all([company, role, start_date]):
                continue

            # Handle nullable end_date
            end_date = exp.get("end_date")
            if end_date in ("", "null", None):
                end_date = None

            try:
                EmploymentHistory.objects.create(
                    freelancer=profile,
                    company=str(company),
                    role=str(role),
                    start_date=start_date,
                    end_date=end_date
                )
            except Exception as e:
                logger.warning(f"Failed to create employment history entry: {e}")

    def _save_portfolio(self, profile, portfolio_list):
        """Replace all portfolio projects for the profile."""
        profile.portfolioproject_set.all().delete()

        if not isinstance(portfolio_list, (list, tuple)):
            return

        for project in portfolio_list:
            if not isinstance(project, dict):
                continue

            title = project.get("title")
            description = project.get("description")

            if not all([title, description]):
                continue

            # Handle optional link
            link = project.get("link")
            if link in ("", "null", None):
                link = None

            try:
                PortfolioProject.objects.create(
                    freelancer=profile,
                    title=str(title),
                    description=str(description),
                    link=link
                )
            except Exception as e:
                logger.warning(f"Failed to create portfolio project: {e}")

    def _save_pricing(self, profile, pricing_list):
        """Replace all pricing entries for the profile."""
        profile.pricing.all().delete()

        if not isinstance(pricing_list, (list, tuple)):
            return

        for pricing_data in pricing_list:
            if not isinstance(pricing_data, dict):
                continue

            pricing_type = pricing_data.get("pricing_type")
            if not pricing_type:
                continue

            try:
                pricing_serializer = PricingSerializer(data=pricing_data)
                if pricing_serializer.is_valid():
                    pricing_serializer.save(freelancer=profile)
                else:
                    logger.warning(f"Invalid pricing data: {pricing_serializer.errors}")
            except Exception as e:
                logger.warning(f"Failed to create pricing entry: {e}")