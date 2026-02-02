from datetime import timedelta
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.db.models import Q
from apps.contract.models import Contract
from apps.freelancer.models import FreelancerProfile

User = settings.AUTH_USER_MODEL


# =====================================================
# Device
# =====================================================
class Device(models.Model):
    freelancer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="devices")
    device_id = models.CharField(max_length=255)
    device_name = models.CharField(max_length=255)
    os_name = models.CharField(max_length=100)
    os_version = models.CharField(max_length=100)

    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("freelancer", "device_id")


# =====================================================
# Work Session
# =====================================================
class WorkSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="work_sessions",
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE,
        related_name="work_sessions",
    )
    device_id = models.CharField(max_length=128)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Session {self.id} – {self.user}"

    @property
    def total_seconds(self):
        """Closed blocks only (billing-safe)."""
        return sum(
            b.total_seconds
            for b in self.time_blocks.all()
            if b.ended_at is not None
        )

    @property
    def live_total_seconds(self):
        """Includes open block (UI only, never billing)."""
        total = self.total_seconds
        open_block = self.time_blocks.filter(ended_at__isnull=True).first()
        if open_block:
            total += int((timezone.now() - open_block.started_at).total_seconds())
        return total

    @property
    def total_idle_seconds(self):
        return sum(
            b.idle_seconds
            for b in self.time_blocks.all()
            if b.ended_at is not None
        )


# =====================================================
# Time Block
# =====================================================
class TimeBlock(models.Model):
    # --------------------------------------------------
    # End reason (how the block ended)
    # --------------------------------------------------
    END_REASON_CHOICES = [
        ("PAUSE", "Paused by user"),
        ("STOP", "Session stopped"),
        ("IDLE", "Ended due to idle"),
        ("SYSTEM_SLEEP", "System sleep"),
    ]

    # --------------------------------------------------
    # Flag source (who decided the flag)
    # --------------------------------------------------
    FLAG_SOURCE_CHOICES = [
        ("NONE", "Not flagged"),
        ("SYSTEM", "System"),
        ("ADMIN", "Admin"),
    ]

    session = models.ForeignKey(
        WorkSession,
        on_delete=models.CASCADE,
        related_name="time_blocks",
    )

    # --------------------------------------------------
    # Timing
    # --------------------------------------------------
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    idle_seconds = models.PositiveIntegerField(default=0)
    end_reason = models.CharField(
        max_length=20,
        choices=END_REASON_CHOICES,
        null=True,
        blank=True,
    )

    # --------------------------------------------------
    # Metrics (calculated once block closes)
    # --------------------------------------------------
    active_seconds = models.PositiveIntegerField(default=0)
    idle_ratio = models.FloatField(default=0.0)

    # --------------------------------------------------
    # Flagging (SYSTEM + ADMIN)
    # --------------------------------------------------
    is_flagged = models.BooleanField(default=False)

    flag_source = models.CharField(
        max_length=10,
        choices=FLAG_SOURCE_CHOICES,
        default="NONE",
    )

    flag_reason = models.TextField(blank=True)
    flagged_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def __str__(self):
        return f"Block {self.id} (Session {self.session_id})"

    @property
    def total_seconds(self):
        if not self.ended_at:
            return 0
        return int((self.ended_at - self.started_at).total_seconds())

    @property
    def worked_seconds(self):
        return max(
            0,
            self.total_seconds - min(self.idle_seconds, self.total_seconds)
        )

    # --------------------------------------------------
    # Idle handling
    # --------------------------------------------------
    def add_idle(self, seconds: int):
        """
        Safe idle accumulation.
        """
        if seconds <= 0 or self.ended_at:
            return
        self.idle_seconds += int(seconds)
        self.save(update_fields=["idle_seconds"])

    # --------------------------------------------------
    # Close block
    # --------------------------------------------------
    def close(self, *, reason: str):
        if self.ended_at:
            return

        self.ended_at = timezone.now()
        self.end_reason = reason

        duration = int((self.ended_at - self.started_at).total_seconds())
        self.idle_seconds = min(self.idle_seconds, duration)

        if duration > 0:
            self.active_seconds = max(0, duration - self.idle_seconds)
            self.idle_ratio = round(self.idle_seconds / duration, 2)

        self.save(update_fields=[
            "ended_at",
            "end_reason",
            "idle_seconds",
            "active_seconds",
            "idle_ratio",
        ])

    # --------------------------------------------------
    # Flag helpers
    # --------------------------------------------------
    def system_flag(self, reason: str):
        """
        Used ONLY by system logic (idle >= threshold).
        """
        self.is_flagged = True
        self.flag_source = "SYSTEM"
        self.flag_reason = reason
        self.flagged_at = timezone.now()
        self.save(update_fields=[
            "is_flagged",
            "flag_source",
            "flag_reason",
            "flagged_at",
        ])

    def admin_flag(self, reason: str):
        """
        Admin can flag regardless of idle.
        """
        self.is_flagged = True
        self.flag_source = "ADMIN"
        self.flag_reason = reason
        self.flagged_at = timezone.now()
        self.save(update_fields=[
            "is_flagged",
            "flag_source",
            "flag_reason",
            "flagged_at",
        ])

    def admin_deflag(self, reason: str = ""):
        """
        Admin can deflag even system-flagged blocks.
        """
        self.is_flagged = False
        self.flag_source = "ADMIN"
        self.flag_reason = reason
        self.flagged_at = timezone.now()
        self.save(update_fields=[
            "is_flagged",
            "flag_source",
            "flag_reason",
            "flagged_at",
        ])

    # --------------------------------------------------
    # Constraints
    # --------------------------------------------------
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session"],
                condition=Q(ended_at__isnull=True),
                name="one_open_block_per_session",
            )
        ]



# =====================================================
# Screenshot Window
# =====================================================
class ScreenshotWindow(models.Model):
    block = models.ForeignKey(
        TimeBlock,
        on_delete=models.CASCADE,
        related_name="windows",
    )

    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    max_count = models.PositiveSmallIntegerField(default=3)
    used_count = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        return f"Window {self.id} (Block {self.block_id})"


# =====================================================
# Screenshot
# =====================================================
class Screenshot(models.Model):
    block = models.ForeignKey(
        TimeBlock,
        on_delete=models.CASCADE,
        related_name="screenshots",
    )
    window = models.ForeignKey(
        ScreenshotWindow,
        on_delete=models.CASCADE,
        related_name="screenshots",
    )

    image = models.ImageField(upload_to="screenshots/")
    taken_at_client = models.DateTimeField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    resolution = models.CharField(max_length=32, default="full")

    # How much idle increased since previous screenshot
    idle_seconds_delta = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"Screenshot {self.id} (Block {self.block_id})"


# =====================================================
# Work Consent
# =====================================================
class WorkConsent(models.Model):
    freelancer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="tracking_consents"
    )
    contract = models.ForeignKey(
        Contract,
        on_delete=models.CASCADE
    )
    policy_version = models.CharField(max_length=20)

    consented_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("freelancer", "contract")
        indexes = [
            models.Index(fields=["freelancer", "contract"]),
            models.Index(fields=["is_active"]),
        ]

    def revoke(self):
        if not self.is_active:
            return
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_active", "revoked_at"])


# =====================================================
# Activity Log
# =====================================================
class ActivityLog(models.Model):
    ACTION_CHOICES = [
        ("SESSION_START", "Session Start"),
        ("SESSION_PAUSE", "Session Pause"),
        ("SESSION_RESUME", "Session Resume"),
        ("SESSION_STOP", "Session Stop"),
        ("BLOCK_START", "Block Start"),
        ("BLOCK_END", "Block End"),
        ("SCREENSHOT", "Screenshot"),
        ("IDLE", "Idle"),
        ("ERROR", "Error"),
    ]

    freelancer = models.ForeignKey(
    FreelancerProfile,
    on_delete=models.CASCADE
    )
    session = models.ForeignKey(
        WorkSession,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    metadata = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]




class TimeBlockExplanation(models.Model):
    block = models.OneToOneField(
        TimeBlock,
        on_delete=models.CASCADE,
        related_name="explanation",
    )

    freelancer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="timeblock_explanations",
    )

    explanation = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    # Admin review
    admin_status = models.CharField(
        max_length=20,
        choices=[
            ("PENDING", "Pending"),
            ("ACCEPTED", "Accepted"),
            ("REJECTED", "Rejected"),
        ],
        default="PENDING",
    )

    admin_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["block"],
                name="one_explanation_per_block",
            )
        ]

    def __str__(self):
        return f"Explanation for Block {self.block_id}"
