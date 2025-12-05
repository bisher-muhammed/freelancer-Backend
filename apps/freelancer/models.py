from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
User = settings.AUTH_USER_MODEL


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE,null=True,blank=True)

class FreelancerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=120)
    bio = models.TextField()
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resume = models.FileField(upload_to='freelancer_resumes/', null=True, blank=True)
    profile_picture = models.ImageField(upload_to='freelancer_profiles/', blank=True, null=True)

class FreelancerSkill(models.Model):
    freelancer = models.ForeignKey(FreelancerProfile, on_delete=models.CASCADE)
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE)
    level = models.PositiveSmallIntegerField(default=1)  # 1-5 rating

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
        ('fixed', 'Fixed Price'),
        ('range', 'Price Range'),
    ]

    freelancer = models.ForeignKey(FreelancerProfile, on_delete=models.CASCADE, related_name="pricing")
    pricing_type = models.CharField(max_length=10, choices=PRICING_TYPE)

    hourly_rate = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    fixed_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    min_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    max_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    is_default = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        if self.is_default:
            # Remove default from others
            Pricing.objects.filter(freelancer=self.freelancer, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

    def clean(self):
        if self.pricing_type == 'hourly' and not self.hourly_rate:
            raise ValidationError("Hourly rate required.")
        if self.pricing_type == 'fixed' and not self.fixed_price:
            raise ValidationError("Fixed price required.")
        if self.pricing_type == 'range':
            if not self.min_price or not self.max_price:
                raise ValidationError("Min and max price required.")
            if self.min_price >= self.max_price:
                raise ValidationError("Min price must be < max price.")




