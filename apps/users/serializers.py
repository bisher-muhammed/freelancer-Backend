from rest_framework import serializers
from django.contrib.auth import get_user_model, authenticate
from .utils import create_and_send_otp, verify_otp
import re
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from .models import ClientProfile
from apps.freelancer.models import FreelancerProfile
from django.db import transaction
from apps.freelancer.serializers import FreelancerProfileSerializer
from .models import Project
from apps.freelancer.models import Skill
from .models import UserSubscription
from django.utils import timezone
from .models import UserSubscription
from apps.adminpanel.models import SubscriptionPlan





User = get_user_model()


# -------- 1️⃣ Send / Resend OTP Serializer --------
class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        """Ensure email is valid and not already registered"""
        value = value.lower().strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", value):
            raise serializers.ValidationError("Enter a valid email address.")
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email is already registered.")
        return value

    def create(self, validated_data):
        """Send or resend OTP"""
        email = validated_data["email"]
        create_and_send_otp(email, purpose="register")
        return {"email": email, "otp_sent": True}


# -------- 2️⃣ Register Form Serializer (with strong password validation) --------
class RegisterFormSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    role = serializers.ChoiceField(choices=[("client", "Client"), ("freelancer", "Freelancer")])
    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Password must contain uppercase, lowercase, number, and special character."
    )
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        value = value.lower().strip()
        if not re.match(r"[^@]+@[^@]+\.[^@]+", value):
            raise serializers.ValidationError("Enter a valid email address.")
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate_password(self, value):
        """Password strength validation"""
        if not re.search(r"[A-Z]", value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        return value

    def validate(self, data):
        if data["password"] != data["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return data


# -------- 3️⃣ Verify OTP Serializer --------
class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField()
    role = serializers.ChoiceField(choices=["client", "freelancer"])
    password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data["email"]
        otp = data["otp"]

        if not verify_otp(email, otp, purpose="register"):
            raise serializers.ValidationError({"otp": "Invalid or expired OTP."})

        # Ensure email isn't already used
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "Email already registered."})

        return data

    @transaction.atomic
    def create(self, validated_data):
        validated_data.pop("otp")
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user



# ---------- 4️⃣ Login Serializer ----------
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, data):
        email = data.get('email').lower().strip()
        password = data.get('password')

        user = authenticate(email=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid email or password.")

        if not user.is_active:
            raise serializers.ValidationError("User account is disabled.")

        refresh = RefreshToken.for_user(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": {
                "id": user.id,
                "email": user.email,
                "username": user.username,
                "role": user.role,
            },
        }


# ---------- 5️⃣ Forgot Password ----------
class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower().strip()
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email not found.")
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        create_and_send_otp(email, purpose="password_reset")
        return {"email": email, "otp_sent": True}


# ---------- 6️⃣ Verify Password Reset OTP ----------
class VerifyPasswordResetOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email").lower().strip()
        otp = data.get("otp")

        if not verify_otp(email, otp, purpose="password_reset"):
            raise serializers.ValidationError({"otp": "Invalid or expired OTP."})
        return data


# ---------- 7️⃣ Reset Password ----------
class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    new_password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={'input_type': 'password'},
        help_text="Password must contain uppercase, lowercase, number, and special character."
    )
    confirm_new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        value = value.lower().strip()
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email not found.")
        return value

    def validate_new_password(self, value):
        """Password strength validation"""
        if not re.search(r"[A-Z]", value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", value):
            raise serializers.ValidationError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        return value

    def validate(self, data):
        if data["new_password"] != data["confirm_new_password"]:
            raise serializers.ValidationError({"confirm_new_password": "Passwords do not match."})
        return data

    def create(self, validated_data):
        email = validated_data["email"]
        new_password = validated_data["new_password"]

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User not found."})

        user.set_password(new_password)
        user.save()
        return {"email": email, "password_reset": True}


class UserMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email"]


# ---------- 8️⃣ Client Profile Serializer ----------
class ClientProfileSerializer(serializers.ModelSerializer):
    # Read-only user fields
    email = serializers.EmailField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    profile_picture = serializers.ImageField(required=False, allow_null=True)

    # Contact number validation
    contact_number = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'^\+?1?\d{9,15}$',
                message='Enter a valid contact number with country code (e.g., +911234567890).'
            )
        ]
    )

    # Rating validation
    rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=2,
        required=False,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(5)
        ]
    )

    # Country validation
    country = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=100
    )

    def validate_country(self, value):
        if value and not value.replace(" ", "").isalpha():
            raise serializers.ValidationError("Country name must contain only letters and spaces.")
        return value.title().strip() if value else value

    # Profile picture validation (extensions + size)
    def validate_profile_picture(self, value):
        if value:
            valid_extensions = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'avif']
            extension = value.name.split('.')[-1].lower()
            if extension not in valid_extensions:
                raise serializers.ValidationError(
                    f"Unsupported file type '{extension}'. Allowed: {', '.join(valid_extensions)}."
                )
            max_size = 5 * 1024 * 1024  # 5MB
            if value.size > max_size:
                raise serializers.ValidationError("Profile picture size should not exceed 5MB.")
        return value

    class Meta:
        model = ClientProfile
        fields = [
            'id',
            'username',
            'email',
            'company_name',
            'contact_number',
            'bio',
            'total_projects_posted',
            'total_spent',
            'rating',
            'verified',
            'profile_picture',
            'country',
            'city',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'verified',
            'username',
            'email',
            'created_at',
            'updated_at',
            'total_projects_posted',
            'total_spent',
        ]

    # Custom validation at the object level
    def validate(self, attrs):
    # Get incoming values or fallback to existing instance values
        company = attrs.get('company_name') or (getattr(self.instance, 'company_name', '') or '')
        bio = attrs.get('bio') or (getattr(self.instance, 'bio', '') or '')

        if not company.strip() and not bio.strip():
            raise serializers.ValidationError("Please provide at least company name or bio.")
        return attrs




    # ✅ Safe create method (future-proof)
    def create(self, validated_data):
        user = self.context['request'].user

        if ClientProfile.objects.filter(user=user).exists():
            raise serializers.ValidationError("Profile already exists for this user.")

        return ClientProfile.objects.create(user=user, **validated_data)

    # ✅ Update only editable fields
    def update(self, instance, validated_data):
        # Prevent updates to read-only user fields
        blocked_fields = ['email', 'username', 'verified']
        for field in blocked_fields:
            validated_data.pop(field, None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance
    


#---------- Project Serializer ----------



class AdminUserSerializer(serializers.ModelSerializer):
    client_profile = ClientProfileSerializer(read_only=True)
    freelancer_profile = FreelancerProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "role",
            "is_active",
            "date_joined",
            "client_profile",
            "freelancer_profile",
        ]
        read_only_fields = ["date_joined"]



        

class ProjectSerializer(serializers.ModelSerializer):
    skills_required = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Skill.objects.all()
    )
    client = UserMiniSerializer(read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "description",
            "category",
            "skills_required",
            "assignment_type",
            "team_size",
            "budget_type",
            "fixed_budget",
            "hourly_min_rate",
            "hourly_max_rate",
            "experience_level",
            "duration",
            "status",
            "created_at",
            "updated_at",
            "client",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "status"]

    # ------------------- VALIDATIONS ------------------- #

    def validate_title(self, value):
        if len(value.strip()) < 5:
            raise serializers.ValidationError("Title must be at least 5 characters long.")
        return value

    def validate_description(self, value):
        if len(value.strip()) < 20:
            raise serializers.ValidationError("Description must be at least 20 characters long.")
        return value

    def validate(self, attrs):
        budget_type = attrs.get("budget_type")
        fixed_budget = attrs.get("fixed_budget")
        hourly_min = attrs.get("hourly_min_rate")
        hourly_max = attrs.get("hourly_max_rate")
        assignment_type = attrs.get("assignment_type")
        team_size = attrs.get("team_size")

        # FIXED
        if budget_type == "fixed":
            if fixed_budget is None:
                raise serializers.ValidationError("Fixed budget amount is required.")

        # HOURLY  (FIXED VALIDATION)
        if budget_type == "hourly":
            if hourly_min is None or hourly_max is None:
                raise serializers.ValidationError("Hourly min and max required.")

            if hourly_min >= hourly_max:
                raise serializers.ValidationError("Hourly min must be < max.")

            if hourly_min <= 0 or hourly_max <= 0:
                raise serializers.ValidationError("Hourly rates must be positive.")

        # TEAM / SINGLE
        if assignment_type == "team" and not team_size:
            raise serializers.ValidationError("Team size is required for team projects.")

        if assignment_type == "single" and team_size:
            raise serializers.ValidationError("Single freelancer projects cannot have a team size.")

        return attrs

    # ------------------- CREATE ------------------- #

    def _get_available_subscription(self, user):
        return (
            user.subscriptions.filter(
                end_date__gt=timezone.now(),
                remaining_projects__gt=0
            )
            .order_by("end_date")
            .first()
        )

    def create(self, validated_data):
        skills = validated_data.pop("skills_required", [])
        client = self.context["request"].user

        subscription = self._get_available_subscription(client)

        if not subscription:
            raise serializers.ValidationError(
                "No available subscription with remaining projects. Buy a new plan to continue."
            )

        # Consume one credit
        subscription.remaining_projects -= 1
        subscription.save()

        project = Project.objects.create(client=client, **validated_data)
        project.skills_required.set(skills)

        return project

    # ------------------- UPDATE ------------------- #

    def update(self, instance, validated_data):
        skills = validated_data.pop("skills_required", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if skills is not None:
            instance.skills_required.set(skills)

        instance.save()
        return instance





class UserSubscriptionSerializer(serializers.ModelSerializer):
    is_active = serializers.SerializerMethodField()

    class Meta:
        model = UserSubscription
        fields = [
            "id",
            "user",
            "plan",
            "start_date",
            "end_date",
            "remaining_projects",
            "is_active",
        ]
        read_only_fields = ["id", "start_date", "end_date", "remaining_projects", "is_active"]

    def get_is_active(self, obj):
        return obj.is_active


                        

class CreatePaymentSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()

    def validate(self, attrs):
        plan_id = attrs.get("plan_id")
        plan = SubscriptionPlan.objects.filter(id=plan_id).first()

        if not plan:
            raise serializers.ValidationError({"plan_id": "Invalid subscription plan."})

        attrs["plan"] = plan
        return attrs


        



  
    


    
    
    
    
    

