from rest_framework.generics import ListAPIView
from rest_framework.filters import OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from .models import LedgerEntry
from .serializers import LedgerEntryAdminSerializer
from .permissions import IsPlatformAdmin


class LedgerEntryAdminListView(ListAPIView):
    """
    Admin-only ledger inspection endpoint.
    Read-only.
    """

    queryset = LedgerEntry.objects.select_related(
        "user",
        "contract",
    )
    serializer_class = LedgerEntryAdminSerializer
    permission_classes = [IsPlatformAdmin]

    filter_backends = [
        DjangoFilterBackend,
        OrderingFilter,
    ]

    filterset_fields = [
        "entry_type",
        "user",
        "contract",
    ]

    ordering_fields = [
        "created_at",
        "amount",
    ]

    ordering = ["-created_at"]
