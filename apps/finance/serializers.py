from apps.finance.models import LedgerEntry
from rest_framework import serializers


class LedgerEntryAdminSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(
        source="user.email",
        read_only=True,
    )

    class Meta:
        model = LedgerEntry
        fields = (
            "id",
            "entry_type",
            "amount",
            "user",
            "user_email",
            "contract",
            "reference_id",
            "created_at",
        )
        read_only_fields = fields


