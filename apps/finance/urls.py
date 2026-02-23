from django.urls import path
from .views import LedgerEntryAdminListView
urlpatterns = [
    path("admin/ledger/", LedgerEntryAdminListView.as_view(), name="admin-ledger-list"),
]
