from apps.notifications.models import ActivityLog, Notification
from rest_framework import serializers
from django.utils.timesince import timesince

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "notif_type",
            "title",
            "message",
            "data",
            "is_read",
            "created_at",
        ]




class AdminActivitySerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = (
            "id",
            "activity_type",
            "description",
            "time_ago",
            "created_at",
        )

    def get_description(self, obj):
        if obj.activity_type == "USER_REGISTERED":
            role = obj.metadata.get("role", "user")
            return f"New {role} registered"

        if obj.activity_type == "PROJECT_CREATED":
            title = obj.metadata.get("title", "New Project")
            return f"New project posted: {title}"

        if obj.activity_type == "PAYMENT_PROCESSED":
            amount = obj.metadata.get("amount")
            return f"Payment processed: ₹{amount}"

        if obj.activity_type == "DISPUTE_OPENED":
            project_id = obj.metadata.get("project_id")
            return f"New dispute opened: Project #{project_id}"

        if obj.activity_type == "CONTRACT_COMPLETED":
            title = obj.metadata.get("title")
            return f"Contract completed: {title}"

        return obj.description

    def get_time_ago(self, obj):
        return f"{timesince(obj.created_at)} ago"



class ClientActivitySerializer(serializers.ModelSerializer):
    description = serializers.SerializerMethodField()
    time_ago = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = (
            "id",
            "activity_type",
            "description",
            "time_ago",
            "created_at",
        )

    def get_description(self, obj):
        meta = obj.metadata or {}

        if obj.activity_type == "PROJECT_CREATED":
            return f"Your project '{meta.get('title', '')}' was created"

        if obj.activity_type == "OFFER_RECEIVED":
            return "You received a new offer response"

        if obj.activity_type == "ESCROW_FUNDED":
            return f"Escrow funded: ₹{meta.get('amount')}"

        if obj.activity_type == "ESCROW_RELEASED":
            return f"Payment released: ₹{meta.get('amount')}"

        if obj.activity_type == "ESCROW_REFUNDED":
            return f"Refund processed: ₹{meta.get('amount')}"

        if obj.activity_type == "CONTRACT_COMPLETED":
            return f"Contract completed for '{meta.get('title', '')}'"

        if obj.activity_type == "DISPUTE_OPENED":
            return "A dispute has been opened"

        return obj.description

    def get_time_ago(self, obj):
        return f"{timesince(obj.created_at)} ago"

    
    