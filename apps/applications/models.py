from decimal import Decimal
from django.db import models, transaction
from django.db.models import Sum
from apps.billing.models import BillingUnit
from apps.users.models import Project
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings
from apps.freelancer.models import FreelancerProfile
import uuid
from datetime import timedelta





User = settings.AUTH_USER_MODEL
class ProjectScoringConfig(models.Model):
    EXPERIENCE_LEVELS = [
        ('entry', 'Entry'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
    ]

    # Experience level this config applies to
    experience_level = models.CharField(
        max_length=20,
        choices=EXPERIENCE_LEVELS,
        unique=True  # Only one config per level
    )

    # Scoring weights (must sum to 1.0)
    skill_weight = models.FloatField(default=0.4)
    experience_weight = models.FloatField(default=0.3)
    budget_weight = models.FloatField(default=0.2)
    reliability_weight = models.FloatField(default=0.1)

    # Auto-reject threshold
    min_final_score = models.FloatField(default=50)
    auto_reject_on_red_flags = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Global Scoring Config"
        verbose_name_plural = "Global Scoring Configs"

    def clean(self):
        # Ensure weights sum to 1
        total = (
            self.skill_weight +
            self.experience_weight +
            self.budget_weight +
            self.reliability_weight
        )
        if abs(total - 1.0) > 1e-6:
            raise ValidationError("All weights must sum to 1.0 (100%).")

    def save(self, *args, **kwargs):
        self.full_clean()  # Enforce validation
        super().save(*args, **kwargs)

    def __str__(self):
        return f"ScoringConfig → {self.experience_level.capitalize()}"



class Proposal(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('shortlisted', 'Shortlisted'),
        ('interviewing', 'Interviewing'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('auto_rejected', 'Auto Rejected'),
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

    rejection_reason = models.TextField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    is_system_managed = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('project', 'freelancer')
        ordering = ['-created_at']

    def clean(self):
        if self.project.status != 'open':
            raise ValidationError("Cannot apply to a closed project.")

        if self.project.budget_type == 'fixed':
            if not self.bid_fixed_price or self.bid_hourly_rate:
                raise ValidationError("Invalid bid for fixed project.")

        if self.project.budget_type == 'hourly':
            if not self.bid_hourly_rate or self.bid_fixed_price:
                raise ValidationError("Invalid bid for hourly project.")



class ProposalScore(models.Model):
    proposal = models.ForeignKey(
        Proposal,
        on_delete=models.CASCADE,
        related_name="scores"
    )

    experience_level = models.CharField(max_length=20, null=True, blank=True)

    # Raw metrics
    skill_match = models.FloatField()
    experience_match = models.FloatField()
    budget_fit = models.FloatField()
    reliability = models.FloatField()

    final_score = models.FloatField(db_index=True)

    red_flags = models.JSONField(default=list, blank=True)

    auto_reject = models.BooleanField(default=False)
    auto_reject_reason = models.TextField(blank=True)

    is_latest = models.BooleanField(default=True)
    scored_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-scored_at']
        indexes = [
            models.Index(fields=['proposal', 'is_latest']),
        ]

    def save(self, *args, **kwargs):
        # Ensure only ONE latest score at a time
        with transaction.atomic():
            if self.is_latest:
                ProposalScore.objects.filter(
                    proposal=self.proposal,
                    is_latest=True
                ).update(is_latest=False)

            # Optional: clamp final_score to 0–100
            self.final_score = min(max(self.final_score, 0), 100)
            super().save(*args, **kwargs)

    def __str__(self):
        return f"Score → Proposal {self.proposal.id} → {self.final_score}"
    


class ChatRoom(models.Model):
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="chat_rooms"
    )

    proposal = models.OneToOneField(
        Proposal,
        on_delete=models.CASCADE,
        related_name="chat_room"
    )

    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="client_chat_rooms"
    )

    freelancer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="freelancer_chat_rooms"
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["client", "created_at"]),
            models.Index(fields=["freelancer", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["proposal"],
                name="unique_chat_per_proposal"
            )
        ]

    def clean(self):
        if self.proposal.project != self.project:
            raise ValidationError("Proposal-project mismatch")

        if self.project.client != self.client:
            raise ValidationError("Client mismatch")

        if self.proposal.freelancer != self.freelancer:
            raise ValidationError("Freelancer mismatch")

        if self.proposal.status != "shortlisted":
            raise ValidationError("Chat allowed only for shortlisted proposals")

    def __str__(self):
        return f"ChatRoom #{self.id} (Proposal {self.proposal_id})"


        

class Message(models.Model):
    chat_room = models.ForeignKey(ChatRoom,on_delete=models.CASCADE,related_name='messages')


    sender = models.ForeignKey(User,on_delete=models.CASCADE, related_name='send_message')

    content = models.TextField()

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


    
    
    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["chat_room", "created_at"]),
        ]

    def __str__(self):
        return f"Message #{self.id} in ChatRoom #{self.chat_room_id}"
    

    
class SavedProject(models.Model):
    freelancer = models.ForeignKey(
        FreelancerProfile,
        on_delete=models.CASCADE,
        related_name="saved_projects"
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name="saved_by_freelancers"
    )
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "saved_projects"
        constraints = [
            models.UniqueConstraint(
                fields=["freelancer", "project"],
                name="unique_freelancer_saved_project"
            )
        ]
        indexes = [
            models.Index(fields=["freelancer", "project"]),
        ]

    def __str__(self):
        return f"{self.freelancer_id} saved {self.project_id}"






class Meeting(models.Model):
    # -------------------------
    # JOIN WINDOW CONFIG
    # -------------------------
    JOIN_EARLY_BUFFER = timedelta(minutes=10)
    JOIN_LATE_BUFFER = timedelta(minutes=5)

    # -------------------------
    # CHOICES
    # -------------------------
    STATUS_CHOICES = (
        ("scheduled", "Scheduled"),
        ("ongoing", "Ongoing"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("no_show", "No Show"),
    )

    MEETING_TYPE_CHOICES = (
        ("interview", "Interview"),
        ("review", "Review"),
    )

    # -------------------------
    # RELATIONS
    # -------------------------
    proposal = models.ForeignKey(
        "applications.Proposal",
        on_delete=models.CASCADE,
        related_name="meetings",
    )

    chat_room = models.ForeignKey(
        "applications.ChatRoom",
        on_delete=models.CASCADE,
        related_name="meetings",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_meetings",
    )

    # -------------------------
    # CORE FIELDS
    # -------------------------
    meeting_type = models.CharField(
        max_length=20,
        choices=MEETING_TYPE_CHOICES,
    )

    zego_room_id = models.CharField(
        max_length=255,
        editable=False,
        db_index=True,
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="scheduled",
    )

    actual_started_at = models.DateTimeField(null=True, blank=True)
    actual_ended_at = models.DateTimeField(null=True, blank=True)

    last_token_issued_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time a Zego token was issued",
    )

    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # -------------------------
    # META
    # -------------------------
    class Meta:
        ordering = ["-start_time"]
        indexes = [
            models.Index(fields=["status", "start_time"]),
            models.Index(fields=["proposal", "meeting_type"]),
            models.Index(fields=["zego_room_id"]),
        ]

    # -------------------------
    # PARTICIPANTS
    # -------------------------
    @property
    def client(self):
        return self.proposal.project.client

    @property
    def freelancer(self):
        return self.proposal.freelancer

    # -------------------------
    # VALIDATION (CREATION ONLY)
    # -------------------------
    def clean(self):
        # ChatRoom must belong to proposal
        if self.chat_room.proposal_id != self.proposal_id:
            raise ValidationError("ChatRoom does not belong to this proposal")

        # 🔥 Creation-only validations
        if not self.pk:
            now = timezone.now()

            if self.start_time < now:
                raise ValidationError("Start time must be in the future")

            if self.end_time <= self.start_time:
                raise ValidationError("End time must be after start time")

            # Meeting type rules
            if self.meeting_type == "interview":
                if self.proposal.status != "shortlisted":
                    raise ValidationError("Interview allowed only for shortlisted proposals")
                if self.created_by != self.client:
                    raise ValidationError("Only client can schedule interview")

            if self.meeting_type == "review":
                if self.proposal.status != "accepted":
                    raise ValidationError("Review allowed only after hiring")

            # Prevent overlapping meetings
            overlapping = Meeting.objects.filter(
                start_time__lt=self.end_time,
                end_time__gt=self.start_time,
                status__in=["scheduled", "ongoing"],
            )

            if overlapping.filter(proposal__project__client=self.client).exists():
                raise ValidationError("Client already has another meeting during this time")

            if overlapping.filter(proposal__freelancer=self.freelancer).exists():
                raise ValidationError("Freelancer already has another meeting during this time")

        # Prevent edits to completed meetings
        if self.pk:
            old = Meeting.objects.get(pk=self.pk)
            if old.status == "completed":
                raise ValidationError("Completed meetings cannot be modified")

    # -------------------------
    # SAVE LOGIC
    # -------------------------
    def save(self, *args, **kwargs):
        if not self.zego_room_id:
            self.zego_room_id = f"mtg-{self.chat_room_id}-{uuid.uuid4().hex[:10]}"

        # 🚨 Validate ONLY on creation
        if not self.pk:
            self.full_clean()

        super().save(*args, **kwargs)

    # -------------------------
    # JOIN + TOKEN AUTHORITY
    # -------------------------
    def is_joinable_now(self):
        now = timezone.now()
        if self.status not in ("scheduled", "ongoing"):
            return False
        return (
            self.start_time - self.JOIN_EARLY_BUFFER
            <= now
            <= self.end_time + self.JOIN_LATE_BUFFER
        )

    def remaining_seconds(self):
        now = timezone.now()
        remaining = int((self.end_time - now).total_seconds())
        return max(0, remaining)

    def can_issue_token(self, cooldown_seconds=30):
        if not self.last_token_issued_at:
            return True
        elapsed = (timezone.now() - self.last_token_issued_at).total_seconds()
        return elapsed >= cooldown_seconds

    def mark_token_issued(self):
        self.last_token_issued_at = timezone.now()
        # 🚫 no full_clean here
        self.save(update_fields=["last_token_issued_at"])

    # -------------------------
    # STATE TRANSITIONS
    # -------------------------
    def mark_ongoing(self):
        if not self.is_joinable_now():
            raise ValidationError("Meeting cannot start at this time")
        if self.status != "scheduled":
            return
        self.status = "ongoing"
        self.actual_started_at = timezone.now()
        self.save(update_fields=["status", "actual_started_at"])

    def mark_completed(self):
        if self.status not in ("scheduled", "ongoing"):
            return
        self.status = "completed"
        self.actual_ended_at = timezone.now()
        self.save(update_fields=["status", "actual_ended_at"])

    def cancel(self):
        if self.status == "completed":
            raise ValidationError("Completed meeting cannot be cancelled")
        self.status = "cancelled"
        self.save(update_fields=["status"])

    def mark_no_show(self):
        if timezone.now() > self.end_time and self.status == "scheduled":
            self.status = "no_show"
            self.save(update_fields=["status"])

    def __str__(self):
        return f"{self.meeting_type} ({self.status}) – Proposal {self.proposal_id}"




def default_offer_valid_until():
    return timezone.now() + timedelta(days=7)

class Offer(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
    ]

    proposal = models.OneToOneField(
        'applications.Proposal',
        on_delete=models.CASCADE,
        related_name='offer'
    )

    client = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_offers'
    )

    freelancer = models.ForeignKey(
        FreelancerProfile,
        on_delete=models.CASCADE,
        related_name="offers"
    )

    
    total_budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total escrow amount paid upfront by client",
        default= Decimal("0.00")
    )

    agreed_hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Hourly rate agreed for payouts"
    )

    estimated_hours = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Optional estimation for clarity"
    )

    message = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['freelancer', 'status']),
            models.Index(fields=['client', 'status']),
        ]

    def clean(self):
        if self.total_budget <= 0:
            raise ValidationError("Total budget must be positive.")

        if self.agreed_hourly_rate <= 0:
            raise ValidationError("Hourly rate must be positive.")

        if self.estimated_hours:
            expected = self.agreed_hourly_rate * self.estimated_hours
            if expected > self.total_budget:
                raise ValidationError(
                    "Estimated hours exceed total escrow budget."
                )

        if self.valid_until <= timezone.now():
            raise ValidationError("Offer expiry must be in the future.")

    def save(self, *args, **kwargs):
        if self.status == 'pending' and self.valid_until <= timezone.now():
            self.status = 'expired'
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def has_escrow(self):
        return hasattr(self, "payment") and self.payment.status == "escrowed"

    def __str__(self):
        return f"Offer #{self.id} → Proposal {self.proposal.id} ({self.status})"
    

    @property
    def total_paid(self):
        """
        Total amount already consumed from escrow.
        Includes approved/locked/paid units.
        """
        total = BillingUnit.objects.filter(
            contract__offer=self,
            status__in=["approved", "locked", "paid"]
        ).aggregate(
            total=Sum("gross_amount")
        )["total"]

        return total or Decimal("0.00")


    @property
    def remaining_budget(self):
        """
        Escrow still available.
        """
        return max(
            Decimal("0.00"),
            self.total_budget - self.total_paid
        )

    @property
    def is_exhausted(self):
        return self.remaining_budget <= 0




class EscrowPayment(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("escrowed", "Escrowed"),
        ("released", "Released"),
        ("refunded", "Refunded"),
        ("failed", "Failed"),
    ]

    offer = models.OneToOneField(
        Offer,
        on_delete=models.CASCADE,
        related_name="payment"
    )

    # 🔥 SINGLE SOURCE OF TRUTH FOR STRIPE
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total escrow amount charged via Stripe"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    stripe_payment_intent_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    escrowed_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)

    refundable_until = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Optional dispute window"
    )

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
        ]

    def clean(self):
        if self.amount != self.offer.total_budget:
            raise ValidationError(
                "Escrow amount must match offer total budget."
            )

    def __str__(self):
        return f"EscrowPayment #{self.id} ({self.status})"





