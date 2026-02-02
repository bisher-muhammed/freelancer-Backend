from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone
from apps.freelancer.models import Category, Skill
from django.core.exceptions import ValidationError
from apps.adminpanel.models import SubscriptionPlan




class UserManager(BaseUserManager):
    """Custom user manager supporting email authentication."""

    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        if not username:
            raise ValueError("Username is required")

        email = self.normalize_email(email)

        user = self.model(
            email=email,
            username=username,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user


    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")  # Force admin role

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, username, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = (
        ("client", "Client"),
        ("freelancer", "Freelancer"),
        ("admin", "Admin"),
    )

    email = models.EmailField(unique=True, db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="client")
    created_at = models.DateTimeField(default=timezone.now)

    # ✅ TIMEZONE FIELDS (THIS IS THE FIX)
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        help_text="User preferred timezone (used for emails & scheduling)"
    )

    last_detected_timezone = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text="Last timezone detected from browser (UI only)"
    )

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["timezone"]), 
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"

    def has_admin_access(self):
        return self.role == "admin" and self.is_staff and self.is_superuser


    


class ClientProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="client_profile")
    company_name = models.CharField(max_length=255, blank=True, null=True)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    total_projects_posted = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    profile_picture = models.ImageField(upload_to='client_profiles/', blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Client Profile: {self.user.username}"

    class Meta:
        db_table = "client_profiles"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["country"]),
            models.Index(fields=["city"]),
            models.Index(fields=["verified"]),
            models.Index(fields=["-rating"]),
            models.Index(fields=["-total_spent"]),
        ]



class Project(models.Model):
    EXPERIENCE_LEVELS = [
        ('entry', 'Entry Level'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]

    ASSIGNMENT_TYPES = [
        ('single', 'Single Freelancer'),
        ('team', 'Team of Freelancers'),
    ]

    BUDGET_TYPES = [
        ('fixed', 'Fixed Price'),
        ('hourly', 'Hourly'),
    ]

    STATUS = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")

    title = models.CharField(max_length=255)
    description = models.TextField()

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    skills_required = models.ManyToManyField(Skill, related_name="projects")

    assignment_type = models.CharField(
        max_length=20, choices=ASSIGNMENT_TYPES, default='single'
    )

    team_size = models.PositiveIntegerField(null=True, blank=True)

    budget_type = models.CharField(max_length=10, choices=BUDGET_TYPES)
    fixed_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    hourly_min_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hourly_max_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVELS)

    duration = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS, default='open')

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.budget_type == "fixed":
            if self.fixed_budget is None:
                raise ValidationError("Fixed budget amount is required.")

        # ----- HOURLY VALIDATION (FIXED) -----
        if self.budget_type == "hourly":
            if self.hourly_min_rate is None or self.hourly_max_rate is None:
                raise ValidationError("Hourly min and max required.")

            if self.hourly_min_rate >= self.hourly_max_rate:
                raise ValidationError("Hourly min must be < max.")

            if self.hourly_min_rate <= 0 or self.hourly_max_rate <= 0:
                raise ValidationError("Hourly rates must be positive.")

        if self.assignment_type == "team" and not self.team_size:
            raise ValidationError("Team size is required for team projects.")

        if self.assignment_type == "single" and self.team_size:
            raise ValidationError("Single freelancer projects cannot have a team size.")

    def __str__(self):
        return f"Project: {self.title} by {self.client.username}"





class UserSubscription(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="subscriptions"
    )
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    start_date = models.DateTimeField(default=timezone.now)
    end_date = models.DateTimeField()
    remaining_projects = models.IntegerField(default=0)

    def save(self, *args, **kwargs):
        # Initialize only when the subscription is created
        if not self.pk:
            if not self.plan:
                raise ValueError("Subscription must have a plan")

            # Set expiry based on plan
            self.end_date = self.start_date + timezone.timedelta(days=self.plan.duration_days)

            # Set project limit
            self.remaining_projects = self.plan.max_projects

        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """Active only if not expired AND user still has projects left."""
        return self.remaining_projects > 0 and self.end_date > timezone.now()

    def __str__(self):
        return f"{self.user.username} - {self.plan.name} ({self.remaining_projects} left)"



