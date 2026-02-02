from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.utils import timezone
from apps.applications.tasks import send_offer_created_email
from apps.applications.tasks import send_offer_created_email
from apps.notifications.services.create_notifications import notify_user
from apps. users.models import Project, ClientProfile, User
from apps. freelancer.models import FreelancerProfile, Skill
from apps.users.serializers import ProjectSerializer
from .models import EscrowPayment, Proposal,ProposalScore,Message,ChatRoom,SavedProject,Meeting,Offer
from django.db.models import Q


# ---------------- Client Info ----------------
class ClientInfoSerializer(serializers.ModelSerializer):
    member_since = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()

    class Meta:
        model = ClientProfile
        fields = [
            'company_name',
            'country',
            'city',
            'verified',
            'member_since',
            'profile_picture',
        ]

    def get_member_since(self, obj):
        return obj.user.created_at.strftime("%B %Y") if obj.user.created_at else None
    
    def get_profile_picture(self, obj):
        if obj.profile_picture:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
            # Fallback if no request in context
            return obj.profile_picture.url
        return None


# ---------------- Skill Serializer ----------------
class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ['id', 'name']


# ---------------- Project Detail ----------------
class ProjectDetailSerializer(serializers.ModelSerializer):
    skills_required = SkillSerializer(many=True, read_only=True)
    client = serializers.SerializerMethodField()
    already_applied = serializers.SerializerMethodField()
    

    class Meta:
        model = Project
        fields = [
            'id',
            'title',
            'description',
            'skills_required',
            'budget_type',
            'fixed_budget',
            'hourly_min_rate',
            'hourly_max_rate',
            'duration',
            'experience_level',
            'status',
            'created_at',
            'client',
            'already_applied',
        ]

    def get_client(self, obj):
        profile = ClientProfile.objects.filter(user=obj.client).first()
        if not profile:
            return None
        # IMPORTANT: Pass the context to the nested serializer
        return ClientInfoSerializer(profile, context=self.context).data

    def get_already_applied(self, obj):
        user = self.context.get('request').user
        if user.is_authenticated:
            return obj.proposals.filter(freelancer=user).exists()
        return False

# ---------------- Proposal Create / Apply ----------------
from rest_framework import serializers
from .models import Proposal

class ProposalCreateSerializer(serializers.ModelSerializer):
    freelancer = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = Proposal
        fields = [
            'project',
            'freelancer',
            'cover_letter',
            'bid_fixed_price',
            'bid_hourly_rate',
        ]

    def validate_cover_letter(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError("Cover letter cannot be empty.")

        if len(value) < 100:
            raise serializers.ValidationError(
                "Cover letter must be at least 100 characters."
            )

        if len(value) > 2000:
            raise serializers.ValidationError(
                "Cover letter cannot exceed 2000 characters."
            )

        if "<script>" in value.lower():
            raise serializers.ValidationError("Invalid content detected.")

        return value

    def validate(self, attrs):
        request = self.context['request']
        user = request.user
        project = attrs['project']

        if project.client == user:
            raise serializers.ValidationError(
                "You cannot apply to your own project."
            )

        if Proposal.objects.filter(
            project=project,
            freelancer=user
        ).exists():
            raise serializers.ValidationError(
                "You have already applied to this project."
            )

        if project.status != 'open':
            raise serializers.ValidationError(
                "This project is not accepting proposals."
            )

        if project.budget_type == 'fixed':
            if not attrs.get('bid_fixed_price'):
                raise serializers.ValidationError(
                    "Fixed bid amount is required."
                )
            if attrs.get('bid_hourly_rate'):
                raise serializers.ValidationError(
                    "Hourly rate is not allowed for fixed projects."
                )

        if project.budget_type == 'hourly':
            if not attrs.get('bid_hourly_rate'):
                raise serializers.ValidationError(
                    "Hourly rate is required."
                )
            if attrs.get('bid_fixed_price'):
                raise serializers.ValidationError(
                    "Fixed bid is not allowed for hourly projects."
                )

        return attrs


class ProposalScorePublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProposalScore
        fields = [
            'final_score',
            'auto_reject',
            'auto_reject_reason',
            'scored_at',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Hide rejection reason unless rejected
        if not instance.auto_reject:
            data.pop('auto_reject_reason', None)

        return data


class MyProposalSerializer(serializers.ModelSerializer):
    project = ProjectDetailSerializer(read_only=True)
    latest_score = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = [
            'id',
            'status',
            'cover_letter',
            'bid_fixed_price',
            'bid_hourly_rate',
            'created_at',
            'project',
            'latest_score',
        ]

    def get_latest_score(self, obj):
        score = obj.scores.filter(is_latest=True).first()
        if not score:
            return None

        return ProposalScorePublicSerializer(score).data


class MessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(source="sender.id", read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "sender_id",
            "content",
            "created_at",
            "is_read",
        ]
        read_only_fields = ["id", "sender_id", "created_at", "is_read"]


# -------------------------
# Base ChatRoom Serializer
# -------------------------
class BaseChatRoomSerializer(serializers.ModelSerializer):
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id",
            "last_message",
            "unread_count",
            "created_at",
        ]

    def get_last_message(self, obj):
        message = obj.messages.order_by("-created_at").first()
        if not message:
            return None
        return {
            "content": message.content,
            "sender_id": message.sender_id,
            "created_at": message.created_at,
        }

    def get_unread_count(self, obj):
        request = self.context["request"]
        return obj.messages.filter(
            is_read=False
        ).exclude(sender=request.user).count()


# -------------------------
# Client ChatRoom Serializer
# -------------------------
class ClientChatRoomSerializer(BaseChatRoomSerializer):
    freelancer = serializers.SerializerMethodField()
    project_title = serializers.CharField(source="project.title", read_only=True)

    class Meta(BaseChatRoomSerializer.Meta):
        fields = BaseChatRoomSerializer.Meta.fields + [
            "project_title",
            "freelancer",
        ]

    def get_freelancer(self, obj):
        freelancer = obj.freelancer
        return {
            "id": freelancer.id,
            "name": freelancer.username,
        }


# -------------------------
# Freelancer ChatRoom Serializer
# -------------------------
class FreelancerChatRoomSerializer(BaseChatRoomSerializer):
    client = serializers.SerializerMethodField()
    project = serializers.SerializerMethodField()

    class Meta(BaseChatRoomSerializer.Meta):
        fields = BaseChatRoomSerializer.Meta.fields + [
            "client",
            "project",
        ]

    def get_client(self, obj):
        client = obj.client
        return {
            "id": client.id,
            "name": client.get_full_name() or client.username,
        }

    def get_project(self, obj):
        project = obj.project
        return {
            "id": project.id,
            "title": project.title,
        }


# -------------------------
# ChatRoom Create Serializer (Client Only)
# -------------------------
class ChatRoomCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatRoom
        fields = ["proposal"]

    def validate(self, attrs):
        request = self.context["request"]
        proposal = attrs["proposal"]

        # Only client who owns the project can create chat room
        if proposal.project.client != request.user:
            raise serializers.ValidationError("You do not own this project.")

        # Only shortlisted proposals can have chat
        if proposal.status != "shortlisted":
            raise serializers.ValidationError("Proposal is not shortlisted.")

        return attrs
    



class ToggleSaveProjectSerializer(serializers.Serializer):
    project_id = serializers.IntegerField()

    def validate(self, attrs):
        freelancer = self.context["freelancer"]
        project_id = attrs["project_id"]

        attrs["freelancer"] = freelancer
        attrs["project"] = Project.objects.filter(id=project_id).first()

        if not attrs["project"]:
            raise serializers.ValidationError("Invalid project.")

        return attrs

    def create(self, validated_data):
        freelancer = validated_data["freelancer"]
        project = validated_data["project"]

        saved = SavedProject.objects.filter(
            freelancer=freelancer,
            project=project
        ).first()

        if saved:
            saved.delete()
            return {
                "saved": False,
                "message": "Project unsaved"
            }

        SavedProject.objects.create(
            freelancer=freelancer,
            project=project
        )
        return {
            "saved": True,
            "message": "Project saved"
        }
    

class SavedProjectListSerializer(serializers.ModelSerializer):
    project = ProjectSerializer()
    saved_at = serializers.DateTimeField()
    
    class Meta:
        model = SavedProject
        fields = (
            "id",
            "project",
            "saved_at",
        )


class MeetingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = "__all__"
        read_only_fields = [
            "zego_room_id",
            "created_by",   
            "status",
            "actual_started_at",
            "actual_ended_at",
            "created_at",
        ]

    def validate(self, attrs):
        """
        Only serializer-level concerns:
        - Required fields presence
        - Immutable fields on update
        """
        if self.instance:
            if self.instance.status in ("completed", "cancelled"):
                raise serializers.ValidationError(
                    "Completed or cancelled meetings cannot be modified."
                )
        return attrs



class MeetingPublicSerializer(serializers.ModelSerializer):
    can_join = serializers.SerializerMethodField()
    is_upcoming = serializers.SerializerMethodField()

    class Meta:
        model = Meeting
        fields = [
            "id",
            "meeting_type",
            "start_time",
            "end_time",
            "status",
            "zego_room_id",
            "can_join",
            "is_upcoming",
        ]

    def get_can_join(self, obj):
        now = timezone.now()

        if obj.status not in ("scheduled", "ongoing"):
            return False

        # Optional: allow joining only 10 mins before
        return obj.start_time - timezone.timedelta(minutes=10) <= now <= obj.end_time

    def get_is_upcoming(self, obj):
        return obj.start_time > timezone.now()



class ProposalDetailSerializer(serializers.ModelSerializer):
    project = ProjectDetailSerializer(read_only=True)
    meetings = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = [
            "id",
            "status",
            "cover_letter",
            "bid_fixed_price",
            "bid_hourly_rate",
            "created_at",
            "project",
            "meetings",
        ]

    def get_meetings(self, obj):
        meetings = obj.meetings.order_by("start_time")
        return MeetingPublicSerializer(
            meetings,
            many=True,
            context=self.context
        ).data



class OfferCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = [
            "proposal",
            "total_budget",
            "agreed_hourly_rate",
            "estimated_hours",
            "message",
            "valid_until",
        ]

    def validate_proposal(self, value):
        request = self.context["request"]
        user = request.user

        if user.role != "client":
            raise serializers.ValidationError(
                "Only clients can create offers."
            )

        if value.project.client != user:
            raise serializers.ValidationError(
                "You do not own this project."
            )

        if value.status != "accepted":
            raise serializers.ValidationError(
                "Offers can only be made to accepted proposals."
            )

        if hasattr(value, "offer"):
            raise serializers.ValidationError(
                "An offer already exists for this proposal."
            )

        return value

    def validate(self, data):
        budget = data.get("total_budget")
        hourly = data.get("agreed_hourly_rate")
        hours = data.get("estimated_hours")

        if budget <= 0:
            raise serializers.ValidationError(
                {"total_budget": "Budget must be greater than zero."}
            )

        if hourly <= 0:
            raise serializers.ValidationError(
                {"agreed_hourly_rate": "Hourly rate must be greater than zero."}
            )

        if hours:
            expected_cost = hourly * hours
            if expected_cost > budget:
                raise serializers.ValidationError(
                    "Estimated hours exceed total budget."
                )

        return data

    def create(self, validated_data):
        request = self.context["request"]
        proposal = validated_data.pop("proposal")

        offer = Offer.objects.create(
            proposal=proposal,
            client=request.user,
            **validated_data
        )

        freelancer_user = proposal.freelancer
        project = proposal.project

        # ✅ Notify Freelancer
        notify_user(
            recipient=freelancer_user,
            notif_type="OFFER_SENT",
            title="You received an offer",
            message=f"Client {request.user.username} sent you an offer for '{project.title}'.",
            data={
                "offer_id": offer.id,
                "project_id": project.id,
            }
        )

        return offer



class OfferReadOnlySerializer(serializers.ModelSerializer):
    project_id = serializers.IntegerField(
        source="proposal.project.id",
        read_only=True
    )
    project_title = serializers.CharField(
        source="proposal.project.title",
        read_only=True
    )

    client_id = serializers.IntegerField(source="client.id", read_only=True)
    client_name = serializers.SerializerMethodField()

    freelancer_id = serializers.IntegerField(source="freelancer.id", read_only=True)
    freelancer_name = serializers.SerializerMethodField()

    is_expired = serializers.SerializerMethodField()
    can_respond = serializers.SerializerMethodField()

    created_at_display = serializers.SerializerMethodField()
    valid_until_display = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            "id",

            # Project
            "project_id",
            "project_title",

            # Client
            "client_id",
            "client_name",

            # Freelancer
            "freelancer_id",
            "freelancer_name",

            # Financial terms
            "total_budget",
            "agreed_hourly_rate",
            "estimated_hours",

            # Offer state
            "message",
            "status",
            "is_expired",
            "can_respond",

            # Dates
            "created_at",
            "created_at_display",
            "valid_until",
            "valid_until_display",
        ]

        read_only_fields = fields

    def get_client_name(self, obj):
        return obj.client.get_full_name() or obj.client.username

    def get_freelancer_name(self, obj):
        user = obj.freelancer.user
        return user.get_full_name() or user.username

    def get_is_expired(self, obj):
        return obj.valid_until < timezone.now()

    def get_can_respond(self, obj):
        return obj.status == "pending" and not self.get_is_expired(obj)

    def get_created_at_display(self, obj):
        return obj.created_at.strftime("%d %b %Y, %I:%M %p")

    def get_valid_until_display(self, obj):
        return obj.valid_until.strftime("%d %b %Y, %I:%M %p")



class OfferAcceptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = []

    def validate(self, data):
        offer = self.instance
        request = self.context["request"]

        if request.user.role != "freelancer":
            raise serializers.ValidationError("Only freelancers can accept offers.")

        if offer.freelancer.user != request.user:
            raise serializers.ValidationError("This offer is not yours.")

        if offer.status != "pending":
            raise serializers.ValidationError("Only pending offers can be accepted.")

        if offer.valid_until < timezone.now():
            raise serializers.ValidationError("This offer has expired.")

        return data

    def save(self, **kwargs):
        offer = self.instance
        offer.status = "accepted"
        offer.save(update_fields=["status"])
        return offer




class OfferRejectSerializer(serializers.ModelSerializer):
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Offer
        fields = ["rejection_reason"]

    def validate(self, attrs):
        request = self.context["request"]
        offer = self.instance

        if request.user.role != "freelancer":
            raise serializers.ValidationError("Only freelancers can reject offers.")

        if offer.freelancer.user != request.user:
            raise serializers.ValidationError("This offer does not belong to you.")

        if offer.status != "pending":
            raise serializers.ValidationError("Only pending offers can be rejected.")

        return attrs

    def save(self, **kwargs):
        offer = self.instance
        offer.status = "rejected"
        offer.save(update_fields=["status"])
        return offer



class OfferAdminSerializer(serializers.ModelSerializer):
    total_paid = serializers.SerializerMethodField()
    remaining_budget = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            "id",
            "total_budget",
            "total_paid",
            "remaining_budget",
            "agreed_hourly_rate",
        ]

    def get_total_paid(self, obj):
        return str(obj.total_paid)

    def get_remaining_budget(self, obj):
        return str(obj.remaining_budget)




