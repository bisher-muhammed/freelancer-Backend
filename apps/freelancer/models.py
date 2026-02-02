from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
User = settings.AUTH_USER_MODEL
from django.core.exceptions import ValidationError
from django.utils import timezone
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    def __str__(self):
        return self.name

class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE,null=True,blank=True)

    def __str__(self):
        return self.name

class FreelancerProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="freelancer_profile"
    )

    title = models.CharField(max_length=120)
    bio = models.TextField()
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    # Platform-level verification (NOT Stripe)
    is_verified = models.BooleanField(
        default=False,
        help_text="Verified by platform admin"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    resume = models.FileField(upload_to="freelancer_resumes/", null=True, blank=True)
    profile_picture = models.ImageField(upload_to="freelancer_profiles/", blank=True, null=True)

    def __str__(self):
        return f"{self.user.email} - Freelancer"

    def can_receive_payouts(self):
        return self.stripe_payouts_enabled is True

    def __str__(self):
        return f"{self.user.email} - Freelancer"
    

    




class FreelancerSkill(models.Model):
    freelancer = models.ForeignKey(FreelancerProfile, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    level = models.PositiveSmallIntegerField(default=1)  

    class Meta:
        unique_together = ('freelancer', 'skill')

class PortfolioProject(models.Model):
    freelancer = models.ForeignKey(FreelancerProfile, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    description = models.TextField()
    link = models.URLField(null=True, blank=True)
    created_at = models.DateField()

class EmploymentHistory(models.Model):
    freelancer = models.ForeignKey(FreelancerProfile, on_delete=models.CASCADE)
    company = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

class Education(models.Model):
    freelancer = models.ForeignKey(FreelancerProfile, on_delete=models.CASCADE)
    institution = models.CharField(max_length=150)
    degree = models.CharField(max_length=120)
    year_completed = models.IntegerField()

class Review(models.Model):
    freelancer = models.ForeignKey(FreelancerProfile, on_delete=models.CASCADE)
    client = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="reviews_written")
    rating = models.PositiveSmallIntegerField()
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)




class Pricing(models.Model):
    PRICING_TYPE = [
        ('hourly', 'Hourly'),
        ('range', 'Hourly Range'),
    ]

    freelancer = models.ForeignKey(
        "FreelancerProfile",
        on_delete=models.CASCADE,
        related_name="pricing"
    )

    pricing_type = models.CharField(
        max_length=10,
        choices=PRICING_TYPE
    )

    # Main hourly rate freelancer expects
    hourly_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    # Optional range (for discovery / negotiation)
    min_hourly_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )
    max_hourly_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True
    )

    is_default = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_default:
            Pricing.objects.filter(
                freelancer=self.freelancer,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def clean(self):
        if self.pricing_type == 'hourly':
            if not self.hourly_rate:
                raise ValidationError("Hourly rate is required.")

        if self.pricing_type == 'range':
            if not self.min_hourly_rate or not self.max_hourly_rate:
                raise ValidationError("Min and max hourly rates are required.")
            if self.min_hourly_rate >= self.max_hourly_rate:
                raise ValidationError("Min hourly rate must be less than max hourly rate.")




