# billing/serializers.py

from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from django.db.models import Sum
from rest_framework import serializers

from apps.applications.models import Offer
from apps.applications.serializers import OfferAdminSerializer

from .models import BillingUnit, Invoice, PayoutBatch
from apps.tracking.models import WorkSession
from django.contrib.auth import get_user_model







class BillingUnitListSerializer(serializers.ModelSerializer):
    productive_time = serializers.IntegerField(
        source="productive_seconds",
        read_only=True,
    )
    offer = OfferAdminSerializer(source="contract.offer", read_only=True)

    class Meta:
        model = BillingUnit
        fields = (
            "id",
            "contract",
            "freelancer",
            "session",
            "period_start",
            "period_end",
            "billable_seconds",
            "idle_seconds",
            "productive_time",
            "hourly_rate",
            "gross_amount",
            "status",
            "payout_batch",
            "created_at",
            "offer",
        )
        read_only_fields = fields



class BillingUnitReviewSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])

    def update(self, instance, validated_data):
        instance.status = (
            "approved" if validated_data["action"] == "approve" else "rejected"
        )
        instance.save(update_fields=["status"])
        return instance



from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from rest_framework import serializers
from apps.billing.models import BillingUnit

# billing/serializers.py

from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from rest_framework import serializers
from apps.billing.models import BillingUnit


class PayoutPreviewSerializer(serializers.Serializer):
    freelancer_id = serializers.IntegerField()
    billing_unit_ids = serializers.ListField(
        child=serializers.IntegerField(),
        read_only=True,
    )
    total_gross = serializers.DecimalField(max_digits=18, decimal_places=2)
    platform_fee = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_net = serializers.DecimalField(max_digits=18, decimal_places=2)

    @classmethod
    def build(cls, *, freelancer, platform_fee_percent=Decimal("10.00")):
        qs = BillingUnit.objects.filter(
            freelancer=freelancer,
            status="approved",
            payout_batch__isnull=True,
        )

        if not qs.exists():
            raise serializers.ValidationError(
                "No approved billing units available for payout."
            )

        total_gross = qs.aggregate(
            total=Sum("gross_amount")
        )["total"] or Decimal("0.00")

        platform_fee = (
            total_gross * platform_fee_percent / Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        total_net = (total_gross - platform_fee).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return cls(
            instance={
                "freelancer_id": freelancer.id,
                "billing_unit_ids": list(qs.values_list("id", flat=True)),
                "total_gross": total_gross,
                "platform_fee": platform_fee,
                "total_net": total_net,
            }
        )




class PayoutConfirmSerializer(serializers.Serializer):
    freelancer_id = serializers.IntegerField()
    platform_fee_percent = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
    )

    def create(self, validated_data):
        freelancer_id = validated_data["freelancer_id"]
        fee_percent = validated_data["platform_fee_percent"]

        with transaction.atomic():
            units = BillingUnit.objects.select_for_update().filter(
                freelancer_id=freelancer_id,
                status="approved",
                payout_batch__isnull=True,
            )

            if not units.exists():
                raise serializers.ValidationError(
                    "No approved billing units available."
                )

            total_gross = units.aggregate(
                total=Sum("gross_amount")
            )["total"] or Decimal("0.00")

            platform_fee = (
                total_gross * fee_percent / Decimal("100")
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            total_net = (total_gross - platform_fee).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

            payout = PayoutBatch.objects.create(
                freelancer_id=freelancer_id,
                total_gross=total_gross,
                platform_fee=platform_fee,
                total_net=total_net,
                status="pending",
            )

            units.update(
                status="locked",
                payout_batch=payout,
            )

        return payout




class PayoutBatchSerializer(serializers.ModelSerializer):
    billing_units_count = serializers.IntegerField(
        source="billing_units.count",
        read_only=True,
    )
    

    class Meta:
        model = PayoutBatch
        fields = (
            "id",
            "freelancer",
            "total_gross",
            "platform_fee",
            "total_net",
            "status",
            "billing_units_count",
            "created_at",
            "paid_at",
        )
        read_only_fields = fields



from django.db.models import Sum
from rest_framework import serializers

from django.db.models import Sum
from rest_framework import serializers

class InvoiceSerializer(serializers.ModelSerializer):
    freelancer_name = serializers.SerializerMethodField()
    payout_batch_id = serializers.UUIDField(
        source="payout_batch.id", read_only=True
    )

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "freelancer_name",
            "payout_batch_id",
            "total_gross",
            "platform_fee",
            "total_net",
            "currency",
            "status",
            "issued_at",
            "created_at",
        ]

    def get_freelancer_name(self, obj):
        user = obj.freelancer.user
        return user.get_full_name() or user.email

    

