from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from apps.tracking.services.activity_logger import log_activity

from apps.billing.services import create_billing_unit_for_session
from apps.tracking.models import (
    ActivityLog,
    Device,
    Screenshot,
    TimeBlock,
    TimeBlockExplanation,
    WorkSession,
    ScreenshotWindow,
    WorkConsent,
)
from apps.tracking.services.timeblock_flagger import evaluate_timeblock_flag


# =====================================================
# Device
# =====================================================
class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = [
            "device_id",
            "device_name",
            "os_name",
            "os_version",
        ]


# =====================================================
# Session Start
# =====================================================
# =====================================================
# Session Start
# =====================================================
class WorkSessionStartSerializer(serializers.Serializer):
    contract_id = serializers.IntegerField()
    device_id = serializers.CharField(max_length=128)

    def create(self, validated_data):
        user = self.context["request"].user
        freelancer = user.freelancer_profile

        with transaction.atomic():
            session = WorkSession.objects.create(
                user=user,
                contract_id=validated_data["contract_id"],
                device_id=validated_data["device_id"],
            )

            TimeBlock.objects.create(session=session)

            log_activity(
                freelancer_profile=freelancer,
                action="SESSION_START",
                session=session,
                metadata={
                    "contract_id": session.contract_id,
                    "device_id": session.device_id,
                },
            )

        return session


# =====================================================
# Pause
# =====================================================
class WorkSessionPauseSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    idle_seconds = serializers.IntegerField(min_value=0, required=False)
    reason = serializers.ChoiceField(
        choices=["PAUSE", "SYSTEM_SLEEP", "IDLE"],
        required=False,
        default="PAUSE",
    )

    def create(self, validated_data):
        idle = validated_data.get("idle_seconds", 0)
        reason = validated_data.get("reason", "PAUSE")

        with transaction.atomic():
            session = WorkSession.objects.select_for_update().get(
                id=validated_data["session_id"],
                ended_at__isnull=True,
            )

            block = session.time_blocks.filter(ended_at__isnull=True).first()
            if not block:
                raise serializers.ValidationError("No active time block")

            if idle > 0:
                block.add_idle(idle)

            block.close(reason=reason)
            evaluate_timeblock_flag(block)

            session.paused_at = timezone.now()
            session.save(update_fields=["paused_at"])

            log_activity(
                freelancer_profile=session.user.freelancer_profile,
                action="SESSION_PAUSE",
                session=session,
                metadata={
                    "idle_seconds": idle,
                    "reason": reason,
                    "block_id": block.id,
                },
            )

        return session


# =====================================================
# Resume
# =====================================================
class WorkSessionResumeSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()

    def create(self, validated_data):
        with transaction.atomic():
            session = WorkSession.objects.select_for_update().get(
                id=validated_data["session_id"],
                ended_at__isnull=True,
            )

            if not session.paused_at:
                raise serializers.ValidationError("Session is not paused")

            if session.time_blocks.filter(ended_at__isnull=True).exists():
                raise serializers.ValidationError("Active block already exists")

            session.paused_at = None
            session.save(update_fields=["paused_at"])

            block = TimeBlock.objects.create(session=session)

            log_activity(
                freelancer_profile=session.user.freelancer_profile,
                action="SESSION_RESUME",
                session=session,
                metadata={
                    "block_id": block.id,
                },
            )

        return block


# =====================================================
# Stop
# =====================================================
class WorkSessionStopSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    idle_seconds = serializers.IntegerField(min_value=0, required=False, default=0)

    def create(self, validated_data):
        idle_seconds = validated_data.get("idle_seconds", 0)

        with transaction.atomic():
            session = WorkSession.objects.select_for_update().get(
                id=validated_data["session_id"],
                ended_at__isnull=True,
            )

            block = session.time_blocks.filter(ended_at__isnull=True).first()
            if block:
                if idle_seconds > 0:
                    block.add_idle(idle_seconds)

                block.close(reason="STOP")
                evaluate_timeblock_flag(block)

            session.ended_at = timezone.now()
            session.paused_at = None
            session.save(update_fields=["ended_at", "paused_at"])

            # Create billing unit
            billing_unit = create_billing_unit_for_session(session)

            log_activity(
                freelancer_profile=session.user.freelancer_profile,
                action="SESSION_STOP",
                session=session,
                metadata={
                    "idle_seconds": idle_seconds,
                    "total_seconds": session.total_seconds,
                    "billing_unit_id": billing_unit.id if billing_unit else None,
                },
            )

        return session


# =====================================================
# Screenshot Upload
# =====================================================
class ScreenshotUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Screenshot
        fields = [
            "image",
            "taken_at_client",
            "resolution",
        ]

    def create(self, validated_data):
        user = self.context["request"].user

        session = (
            WorkSession.objects.filter(
                user=user,
                ended_at__isnull=True,
                paused_at__isnull=True,
            )
            .order_by("-started_at")
            .first()
        )

        if not session:
            raise serializers.ValidationError("No active session")

        block = session.time_blocks.filter(ended_at__isnull=True).first()
        if not block:
            raise serializers.ValidationError("No active time block")

        now = timezone.now()

        window = (
            block.windows.filter(end_at__gt=now)
            .order_by("-start_at")
            .first()
        )

        if not window:
            window = ScreenshotWindow.objects.create(
                block=block,
                start_at=now,
                end_at=now + timedelta(minutes=10),
            )

        if window.used_count >= window.max_count:
            raise serializers.ValidationError("Screenshot limit reached")

        with transaction.atomic():
            screenshot = Screenshot.objects.create(
                block=block,
                window=window,
                **validated_data,
            )

            window.used_count += 1
            window.save(update_fields=["used_count"])

            log_activity(
                freelancer_profile=user.freelancer_profile,
                action="SCREENSHOT",
                session=session,
                metadata={
                    "block_id": block.id,
                    "window_id": window.id,
                    "resolution": validated_data.get("resolution"),
                },
            )

        return screenshot


# =====================================================
# Idle Flush
# =====================================================
class IdleFlushSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    idle_seconds = serializers.IntegerField(min_value=1)

    def create(self, validated_data):
        with transaction.atomic():
            session = WorkSession.objects.select_for_update().get(
                id=validated_data["session_id"],
                ended_at__isnull=True,
                paused_at__isnull=True,
            )

            block = session.time_blocks.filter(ended_at__isnull=True).first()
            if not block:
                raise serializers.ValidationError("No active block")

            block.add_idle(validated_data["idle_seconds"])

            log_activity(
                freelancer_profile=session.user.freelancer_profile,
                action="IDLE",
                session=session,
                metadata={
                    "idle_seconds": validated_data["idle_seconds"],
                    "block_id": block.id,
                },
            )

        return block

# =====================================================
# Read serializers
# =====================================================
class TimeBlockSerializer(serializers.ModelSerializer):
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = TimeBlock
        fields = [
            "id",
            "session",
            "started_at",
            "ended_at",
            "duration_seconds",
            "active_seconds",
            "idle_seconds",
            "idle_ratio",
            "end_reason",
            "is_flagged",
            "flag_reason",
            "created_at",
        ]
        read_only_fields = fields  # HARD READ-ONLY

    def get_duration_seconds(self, obj):
        if not obj.ended_at:
            return None
        return int((obj.ended_at - obj.started_at).total_seconds())



class FreelancerScreenshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Screenshot
        fields = [
            "id",
            "image",
            "taken_at_client",
            "uploaded_at",
            "resolution",
        ]


class ScreenshotWindowDetailSerializer(serializers.ModelSerializer):
    screenshots = FreelancerScreenshotSerializer(many=True, read_only=True)

    class Meta:
        model = ScreenshotWindow
        fields = [
            "id",
            "start_at",
            "end_at",
            "max_count",
            "used_count",
            "screenshots",
        ]


class FreelancerTimeBlockSerializer(TimeBlockSerializer):
    windows = ScreenshotWindowDetailSerializer(many=True, read_only=True)

    class Meta(TimeBlockSerializer.Meta):
        fields = TimeBlockSerializer.Meta.fields + ["windows"]


class WorkSessionDetailSerializer(serializers.ModelSerializer):
    time_blocks = FreelancerTimeBlockSerializer(many=True, read_only=True)

    class Meta:
        model = WorkSession
        fields = [
            "id",
            "started_at",
            "ended_at",
            "total_seconds",
            "time_blocks",
        ]
        read_only_fields = fields


class FreelancerSessionListSerializer(serializers.ModelSerializer):
    total_seconds = serializers.IntegerField(read_only=True)

    class Meta:
        model = WorkSession
        fields = [
            "id",
            "contract_id",
            "started_at",
            "ended_at",
            "total_seconds",
        ]
        read_only_fields = fields



class TimeBlockExplanationCreateSerializer(serializers.ModelSerializer):
    block_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = TimeBlockExplanation
        fields = ["block_id", "explanation"]

    def validate(self, attrs):
        user = self.context["request"].user
        block_id = attrs["block_id"]

        try:
            block = TimeBlock.objects.select_related("session").get(id=block_id)
        except TimeBlock.DoesNotExist:
            raise serializers.ValidationError("Invalid time block")

        if block.session.user != user:
            raise serializers.ValidationError("Not your time block")

        if not block.is_flagged:
            raise serializers.ValidationError("Block is not flagged")

        if hasattr(block, "explanation"):
            raise serializers.ValidationError("Explanation already submitted")

        attrs["block"] = block
        attrs["freelancer"] = user
        return attrs

    def create(self, validated_data):
        validated_data.pop("block_id")
        return super().create(validated_data)



class TimeBlockExplanationReviewSerializer(serializers.Serializer):
    admin_status = serializers.ChoiceField(
        choices=["ACCEPTED", "REJECTED"]
    )
    admin_note = serializers.CharField(required=False, allow_blank=True)

    def update(self, instance, validated_data):
        admin_status = validated_data["admin_status"]
        admin_note = validated_data.get("admin_note", "")

        instance.admin_status = admin_status
        instance.admin_note = admin_note
        instance.reviewed_at = timezone.now()
        instance.save(update_fields=[
            "admin_status",
            "admin_note",
            "reviewed_at",
        ])

        block = instance.block

        # Admin decision is FINAL
        if admin_status == "ACCEPTED":
            block.admin_deflag(
                reason="Admin accepted explanation"
            )
        else:
            block.admin_flag(
                reason="Admin rejected explanation"
            )

        return instance





class TimeBlockFlagUpdateSerializer(serializers.Serializer):
    is_flagged = serializers.BooleanField()
    flag_reason = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    def update(self, instance, validated_data):
        is_flagged = validated_data["is_flagged"]
        reason = validated_data.get("flag_reason", "").strip()

        if is_flagged:
            instance.admin_flag(
                reason=reason or "Flagged by admin"
            )
        else:
            instance.admin_deflag(
                reason=reason or "Deflagged by admin"
            )

        return instance



class ActivityLogSerializer(serializers.ModelSerializer):
    freelancer_name = serializers.CharField(
        source="freelancer.user.username",
        read_only=True
    )

    session_id = serializers.IntegerField(
        source="session.id",
        read_only=True
    )

    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "freelancer_name",
            "session_id",
            "action",
            "metadata",
            "created_at",
        ]