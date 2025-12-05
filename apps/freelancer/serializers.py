from rest_framework import serializers
from .models import (
    Category, Skill, FreelancerProfile, FreelancerSkill,
    PortfolioProject, EmploymentHistory, Education, Review,
    Pricing
)
from apps.users.models import User
from django.core.validators import RegexValidator
from django.db import transaction
import logging
import json

logger = logging.getLogger(__name__)


# ----------------------------
# Custom Field for Flexible JSON/List Input
# ----------------------------
class FlexibleJSONField(serializers.Field):
    """
    A field that accepts JSON strings, Python lists/dicts, or comma-separated strings.
    Handles data from both FormData (JSON strings) and JSON requests (already parsed).
    """
    def to_internal_value(self, data):
        """Convert incoming data to Python object."""
        # If it's already a list or dict, return as is
        if isinstance(data, (list, dict)):
            return data
        
        # If it's a string, try to parse as JSON
        if isinstance(data, str):
            # Try JSON parsing first
            try:
                return json.loads(data)
            except (json.JSONDecodeError, ValueError):
                # If not valid JSON, treat as comma-separated string
                if ',' in data:
                    return [item.strip() for item in data.split(',') if item.strip()]
                # Single value
                return [data.strip()] if data.strip() else []
        
        # For None or empty values
        if data is None or data == '':
            return []
        
        # Fallback: try to convert to list
        return list(data) if data else []
    
    def to_representation(self, value):
        """Convert Python object to representation (for responses)."""
        return value

# ----------------------------
# Base Serializers
# ----------------------------
class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']


class SkillSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source='category', write_only=True, required=False
    )

    class Meta:
        model = Skill
        fields = ['id', 'name', 'category', 'category_id']


class FreelancerSkillSerializer(serializers.ModelSerializer):
    skill = SkillSerializer(read_only=True)
    skill_id = serializers.PrimaryKeyRelatedField(
        queryset=Skill.objects.all(), source='skill', write_only=True
    )

    class Meta:
        model = FreelancerSkill
        fields = ['id', 'skill', 'skill_id', 'level']
        read_only_fields = ['id']


class PortfolioProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = PortfolioProject
        fields = ['id', 'title', 'description', 'link', 'created_at']
        read_only_fields = ['id']


class EmploymentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EmploymentHistory
        fields = ['id', 'company', 'role', 'start_date', 'end_date']
        read_only_fields = ['id']

    def validate(self, data):
        if data.get('end_date') and data['end_date'] < data['start_date']:
            raise serializers.ValidationError("End date cannot be before start date.")
        return data


class EducationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Education
        fields = ['id', 'institution', 'degree', 'year_completed']
        read_only_fields = ['id']

    def validate_year_completed(self, value):
        if value > 2100 or value < 1950:
            raise serializers.ValidationError("Year is unrealistic.")
        return value


class ReviewSerializer(serializers.ModelSerializer):
    client = serializers.StringRelatedField(read_only=True)
    client_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(), source='client', write_only=True
    )

    class Meta:
        model = Review
        fields = ['id', 'client', 'client_id', 'rating', 'comment', 'created_at']
        read_only_fields = ['created_at', 'id']

    def validate_rating(self, value):
        if value < 1 or value > 5:
            raise serializers.ValidationError("Rating must be between 1-5")
        return value


class PricingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pricing
        fields = [
            'id', 'pricing_type',
            'hourly_rate', 'fixed_price', 'min_price', 'max_price',
            'is_default'
        ]
        read_only_fields = ['id']

    def validate(self, data):
        pricing_type = data.get('pricing_type')
        if pricing_type == 'hourly' and not data.get('hourly_rate'):
            raise serializers.ValidationError("Hourly rate is required.")
        if pricing_type == 'fixed' and not data.get('fixed_price'):
            raise serializers.ValidationError("Fixed price is required.")
        if pricing_type == 'range':
            if not data.get('min_price') or not data.get('max_price'):
                raise serializers.ValidationError("Min & Max required.")
            if data['min_price'] >= data['max_price']:
                raise serializers.ValidationError("Min must be less than max.")
        return data


# ----------------------------
# Freelancer Profile Serializer
# ----------------------------
class FreelancerProfileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    skills_read = serializers.SerializerMethodField()
    education = serializers.SerializerMethodField()
    experience = serializers.SerializerMethodField()

    skills_names = serializers.SerializerMethodField()
    categories_names = serializers.SerializerMethodField()

    # Write-only inputs - use custom flexible field
    skills = FlexibleJSONField(write_only=True, required=False)
    categories = FlexibleJSONField(write_only=True, required=False)
    education_input = FlexibleJSONField(write_only=True, required=False)
    experience_input = FlexibleJSONField(write_only=True, required=False)

    # File fields (optional)
    resume = serializers.FileField(required=False, allow_null=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)

    contact_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        validators=[RegexValidator(
            regex=r'^\+?1?\d{9,15}$',
            message='Invalid phone number format. Use +911234567890'
        )]
    )

    class Meta:
        model = FreelancerProfile
        fields = [
            'id', 'user', 'username', 'email',
            'title', 'bio', 'contact_number', 'hourly_rate',
            'is_verified', 'resume', 'profile_picture',
            'created_at', 'updated_at',
            'skills', 'skills_read', 'skills_names',
            'categories', 'categories_names',
            'education', 'education_input',
            'experience', 'experience_input'
        ]
        read_only_fields = ['id', 'username', 'email', 'user', 'is_verified', 'created_at', 'updated_at']

    # ----------------------------
    # READ HELPERS
    # ----------------------------
    def get_skills_read(self, obj):
        return FreelancerSkillSerializer(
            obj.freelancerskill_set.select_related("skill", "skill__category"),
            many=True
        ).data

    def get_education(self, obj):
        return EducationSerializer(obj.education_set.all(), many=True).data

    def get_experience(self, obj):
        return EmploymentHistorySerializer(obj.employmenthistory_set.all(), many=True).data

    def get_skills_names(self, obj):
        return list(
            obj.freelancerskill_set.select_related("skill").values_list("skill__name", flat=True)
        )

    def get_categories_names(self, obj):
        return list(
            obj.freelancerskill_set.select_related("skill__category")
            .values_list("skill__category__name", flat=True)
            .distinct()
        )

    # ----------------------------
    # CREATE / UPDATE
    # ----------------------------
    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user

        # Extract structured inputs (default to empty lists)
        skills = validated_data.pop("skills", []) or []
        categories = validated_data.pop("categories", []) or []
        education = validated_data.pop("education_input", []) or []
        experience = validated_data.pop("experience_input", []) or []

        # Handle files if present in validated_data
        profile_picture = validated_data.pop("profile_picture", None)
        resume = validated_data.pop("resume", None)

        # Create profile (remaining validated_data contains simple fields)
        profile = FreelancerProfile.objects.create(user=user, **validated_data)

        # Save files if provided
        if profile_picture and hasattr(profile_picture, 'read'):
            profile.profile_picture = profile_picture
        if resume and hasattr(resume, 'read'):
            profile.resume = resume

        profile.save()

        # Save nested lists
        self._save_skills(profile, skills, categories)
        self._save_education(profile, education)
        self._save_experience(profile, experience)

        return profile

    @transaction.atomic
    def update(self, instance, validated_data):
        # Extract input arrays (if present). None means the client explicitly wants removal/empty.
        skills = validated_data.pop("skills", None)
        categories = validated_data.pop("categories", None)
        education = validated_data.pop("education_input", None)
        experience = validated_data.pop("experience_input", None)

        # Handle file fields from validated_data.
        # FIXED: Check if the value is actually a file, not just if key exists
        profile_picture = validated_data.pop("profile_picture", serializers.empty)
        resume = validated_data.pop("resume", serializers.empty)

        # Update other fields normally
        for key, value in validated_data.items():
            setattr(instance, key, value)

        # Handle file updates
        # Only update if a new file was provided or explicitly set to None/empty
        if profile_picture is not serializers.empty:
            if profile_picture is None or profile_picture == '':
                # Explicitly remove the file
                if instance.profile_picture:
                    instance.profile_picture.delete(save=False)
                instance.profile_picture = None
            elif hasattr(profile_picture, 'read'):  # It's a file object
                # Replace with new file
                if instance.profile_picture:
                    instance.profile_picture.delete(save=False)
                instance.profile_picture = profile_picture

        if resume is not serializers.empty:
            if resume is None or resume == '':
                # Explicitly remove the file
                if instance.resume:
                    instance.resume.delete(save=False)
                instance.resume = None
            elif hasattr(resume, 'read'):  # It's a file object
                # Replace with new file
                if instance.resume:
                    instance.resume.delete(save=False)
                instance.resume = resume

        instance.save()

        # Update nested relations only if client provided them
        if skills is not None:
            # categories may be None or list; ensure a list for mapping
            self._save_skills(instance, skills or [], categories or [])
        if education is not None:
            self._save_education(instance, education or [])
        if experience is not None:
            self._save_experience(instance, experience or [])

        return instance

    # ----------------------------
    # INTERNAL WRITE HELPERS
    # ----------------------------
    def _save_skills(self, profile, skills, categories):
        """Save skills - data is already parsed by FlexibleJSONField."""
        if not isinstance(skills, (list, tuple)):
            skills = []
        if not isinstance(categories, (list, tuple)):
            categories = []

        # Remove existing and recreate
        profile.freelancerskill_set.all().delete()

        for index, skill_name in enumerate(skills):
            if not skill_name:
                continue
            
            # Convert to string if needed
            s_name = str(skill_name).strip() if skill_name else None
            if not s_name:
                continue

            # Get corresponding category
            if index < len(categories) and categories[index]:
                category_name = str(categories[index]).strip()
            else:
                category_name = "General"
            
            category, _ = Category.objects.get_or_create(name=category_name)
            skill_obj, _ = Skill.objects.get_or_create(name=s_name, defaults={"category": category})
            
            FreelancerSkill.objects.create(
                freelancer=profile,
                skill=skill_obj,
                level=3,  # default
            )

    def _save_education(self, profile, education_list):
        """Save education - data is already parsed by FlexibleJSONField."""
        profile.education_set.all().delete()
        
        if not isinstance(education_list, (list, tuple)):
            return
        
        for edu in education_list:
            if not isinstance(edu, dict):
                continue
            
            institution = edu.get("institution")
            degree = edu.get("degree")
            year_completed = edu.get("year_completed") or edu.get("year")
            
            if not institution or not degree or not year_completed:
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
                continue

    def _save_experience(self, profile, experience_list):
        """Save experience - data is already parsed by FlexibleJSONField."""
        profile.employmenthistory_set.all().delete()
        
        if not isinstance(experience_list, (list, tuple)):
            return
        
        for exp in experience_list:
            if not isinstance(exp, dict):
                continue
            
            company = exp.get("company")
            role = exp.get("role")
            start_date = exp.get("start_date")
            
            if not company or not role or not start_date:
                continue
            
            end_date = exp.get("end_date")
            # Handle empty string as None
            if end_date == "" or end_date == "null":
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
                logger.warning(f"Failed to create experience entry: {e}")
                continue

