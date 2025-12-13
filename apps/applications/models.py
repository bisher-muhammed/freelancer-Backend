from django.db import models
from apps.users.models import User,Project
from django.core.exceptions import ValidationError
from django.utils import timezone





class Proposal(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('shortlisted', 'Shortlisted'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]

    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="proposals"
    )

    freelancer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="proposals"
    )

    cover_letter = models.TextField()

    # Bid fields (only one is valid depending on project.budget_type)
    bid_fixed_price = models.DecimalField(
        max_digits=12, decimal_places=2,
        null=True, blank=True
    )

    bid_hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='submitted'
    )

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('project', 'freelancer')
        ordering = ['-created_at']

    def clean(self):
        # Cannot apply to non-open projects
        if self.project.status != 'open':
            raise ValidationError("Cannot apply to a closed project.")

        # Fixed budget validation
        if self.project.budget_type == 'fixed':
            if not self.bid_fixed_price:
                raise ValidationError("Fixed bid price is required.")
            if self.bid_hourly_rate:
                raise ValidationError("Hourly bid not allowed for fixed projects.")

        # Hourly budget validation
        if self.project.budget_type == 'hourly':
            if not self.bid_hourly_rate:
                raise ValidationError("Hourly bid rate is required.")
            if self.bid_fixed_price:
                raise ValidationError("Fixed bid not allowed for hourly projects.")

    def __str__(self):
        return f"{self.freelancer.username} → {self.project.title}"

