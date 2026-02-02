from rest_framework import serializers
from apps.adminpanel.models import TrackingPolicy
from apps.applications.models import EscrowPayment, Offer
from apps.contract.models import Contract, ContractDocument, ContractDocumentFolder
from apps.contract.utils.file_validation import validate_contract_document
from apps.tracking.models import Device, WorkConsent
from django.db import transaction



class TrackingPolicyMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingPolicy
        fields = ["id", "version", "title"]


class OfferSummarySerializer(serializers.ModelSerializer):
    # Derived field: type of rate
    rate_type = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = [
            "id",
            "total_budget",
            "agreed_hourly_rate",
            "estimated_hours",
            "rate_type",
            "created_at",
            "status",
        ]

    def get_rate_type(self, obj):
        # if agreed_hourly_rate > 0 → hourly, otherwise fixed
        return "hourly" if obj.agreed_hourly_rate else "fixed"


class EscrowPaymentSerializer(serializers.ModelSerializer):
    # Frontend expects stripe_session_id → alias for actual field
    stripe_session_id = serializers.SerializerMethodField()

    class Meta:
        model = EscrowPayment
        fields = [
            "id",
            "amount",
            "status",
            "stripe_session_id",
            "created_at",
            "escrowed_at",
            "released_at",
            "refunded_at",
            "refundable_until",
        ]

    def get_stripe_session_id(self, obj):
        return obj.stripe_payment_intent_id


class ContractSerializer(serializers.ModelSerializer):
    # Basic references
    freelancer_name = serializers.CharField(source="offer.freelancer.username", read_only=True)
    client_name = serializers.CharField(source="offer.client.username", read_only=True)
    project_title = serializers.CharField(source="offer.proposal.project.title", read_only=True)

    # Embed related objects
    offer = OfferSummarySerializer(read_only=True)
    escrow_payment = EscrowPaymentSerializer(source="offer.payment", read_only=True)

    # Tracking
    tracking_required = serializers.BooleanField(read_only=True)
    tracking_policy = TrackingPolicyMiniSerializer(read_only=True)

    # Extra fields
    policy_accepted = serializers.SerializerMethodField()
    chat_room_id = serializers.SerializerMethodField()
    current_user_id = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = [
            "id",

            # People
            "freelancer_name",
            "client_name",

            # Project
            "project_title",
            "scope_summary",

            # Payment
            "offer",
            "escrow_payment",

            # Platform Rules
            "platform_fee_percentage",
            "termination_notice_days",

            # Status
            "status",
            "started_at",
            "ended_at",
            "completed_at",
            "terminated_at",

            # Tracking
            "tracking_required",
            "tracking_policy",
            "policy_accepted",

            # Chat
            "chat_room_id",
            "current_user_id",

            # Timestamps
            "created_at",
            "updated_at",
        ]

    def get_chat_room_id(self, obj):
        proposal = obj.offer.proposal
        return proposal.chat_room.id if hasattr(proposal, "chat_room") else None

    def get_current_user_id(self, obj):
        request = self.context.get("request")
        return request.user.id if request else None

    def get_policy_accepted(self, obj):
        request = self.context.get("request")
        user = request.user if request else None
        if not user:
            return False
        return WorkConsent.objects.filter(contract=obj, freelancer=user, is_active=True).exists()

    



class AcceptTrackingPolicySerializer(serializers.Serializer):
    """
    Freelancer explicitly accepts the active tracking policy
    """
    contract_id = serializers.IntegerField()

    def validate(self, attrs):
        request = self.context["request"]
        user = request.user

        if user.role != "freelancer":
            raise serializers.ValidationError("Only freelancers can accept tracking policies.")

        # 🔹 Get the freelancer profile
        freelancer_profile = getattr(user, "freelancer_profile", None)
        if not freelancer_profile:
            raise serializers.ValidationError("User does not have a freelancer profile.")

        # 🔹 Correctly filter contract via FreelancerProfile
        contract = Contract.objects.filter(
            id=attrs["contract_id"],
            offer__freelancer=freelancer_profile
        ).first()
        if not contract:
            raise serializers.ValidationError("Invalid contract or not accessible.")

        # 🔹 Prevent duplicate consent
        if WorkConsent.objects.filter(
            freelancer=user,
            contract=contract,
            is_active=True
        ).exists():
            raise serializers.ValidationError("Tracking already accepted on this contract.")

        # 🔹 Active policy check
        policy = TrackingPolicy.objects.filter(is_active=True).first()
        if not policy:
            raise serializers.ValidationError("No active tracking policy.")

        attrs["contract"] = contract
        attrs["policy"] = policy
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        user = self.context["request"].user
        contract = validated_data["contract"]
        policy = validated_data["policy"]

        # 🔹 Create WorkConsent
        consent = WorkConsent.objects.create(
            freelancer=user,
            contract=contract,
            policy_version=policy.version,
            is_active=True
        )

        # 🔹 Update contract tracking flags
        contract.tracking_required = True
        contract.tracking_policy = policy
        contract.save(update_fields=["tracking_required", "tracking_policy"])

        return consent


class TrackingPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingPolicy
        fields = ['id', 'version', 'title', 'content', 'is_active', 'created_at']
        read_only_fields = fields



class ContractDocumentFolderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContractDocumentFolder
        fields = [
            "id",
            "name",
            "created_at",
        ]


class ContractDocumentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(
        source="uploaded_by.username",
        read_only=True
    )
    folder_name = serializers.CharField(
        source="folder.name",
        read_only=True
    )
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = ContractDocument
        fields = [
            "id",
            "original_name",
            "mime_type",          
            "file_url",
            "uploaded_by_name",
            "folder",
            "folder_name",
            "created_at",
        ]
        read_only_fields = [
            "original_name",
            "mime_type",  # Keep this as read_only - we'll set it in create/update
            "uploaded_by_name",
            "created_at",
        ]

    def get_file_url(self, obj):
        request = self.context.get("request")
        if request and obj.file:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url if obj.file else None

    def validate(self, attrs):
        """
        Centralized validation
        """
        request = self.context.get("request")
        if not request:
            return attrs

        uploaded_file = request.FILES.get("file")
        validate_contract_document(uploaded_file)

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        uploaded_file = request.FILES.get('file')
        
        # Set the mime_type from the uploaded file
        if uploaded_file:
            validated_data['mime_type'] = uploaded_file.content_type
        
        # Also set original_name from the uploaded file
        if uploaded_file:
            validated_data['original_name'] = uploaded_file.name
        
        # Set uploaded_by from the request user
        validated_data['uploaded_by'] = request.user
        
        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context.get('request')
        uploaded_file = request.FILES.get('file') if request else None
        
        # If a new file is uploaded, update the mime_type
        if uploaded_file:
            validated_data['mime_type'] = uploaded_file.content_type
            validated_data['original_name'] = uploaded_file.name
        
        return super().update(instance, validated_data)