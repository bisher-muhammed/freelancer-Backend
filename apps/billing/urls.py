# billing/urls.py
from django.urls import path
from .views import (
    AdminBillingUnitDetailView,
    AdminBillingUnitListView,
    AdminRevenueSummaryView,
    BillingUnitReviewView,
    FreelancerBillingUnitListView,
    AdminPayoutPreviewView,
    FreelancerEarningsSummaryView,
    FreelancerMonthlyEarningsView,
    InvoiceDetailView,
    InvoiceListView,
    PayoutConfirmView,
)

urlpatterns = [
    # -------- Admin : Billing Units --------
    path(
        "admin/billing-units/",
        AdminBillingUnitListView.as_view(),
        name="admin-billing-unit-list",
    ),
    path(
        "admin/billing-units/<int:billing_id>/review/",
        BillingUnitReviewView.as_view(),
        name="admin-billing-unit-review",
    ),

    # -------- Freelancer --------
    path(
        "freelancer/billing-units/",
        FreelancerBillingUnitListView.as_view(),
        name="freelancer-billing-unit-list",
    ),

    # -------- Admin : Payouts --------
    path(
        "admin/payouts/preview/",
        AdminPayoutPreviewView.as_view(),
        name="admin-payout-preview",
    ),
    path(
        "admin/payouts/confirm/",
        PayoutConfirmView.as_view(),
        name="admin-payout-confirm",
    ),
    path(
        "billing/admin/billing-units/<int:billing_id>/",
        AdminBillingUnitDetailView.as_view(),  
        name="admin-billing-unit-detail",
    ),

       # -------- Invoices (Admin + Freelancer) --------
    path("invoices/", InvoiceListView.as_view(), name="invoice-list"),
    path("invoices/<uuid:id>/", InvoiceDetailView.as_view(), name="invoice-detail"),

    # -------- Freelancer Earnings --------
    path(
        "freelancer/earnings/summary/",
        FreelancerEarningsSummaryView.as_view(),
        name="freelancer-earnings-summary",
    ),
    path(
        "freelancer/earnings/monthly/",
        FreelancerMonthlyEarningsView.as_view(),
        name="freelancer-monthly-earnings",
    ),

    # -------- Admin Revenue --------
    path(
        "admin/revenue/summary/",
        AdminRevenueSummaryView.as_view(),
        name="admin-revenue-summary",
    ),
]


