# apps/invoicing/selectors.py
from django.db.models import Sum
from django.db.models.functions import TruncMonth
from .models import Invoice


class InvoiceAccessSelector:
    """
    Centralized read-access logic for invoice objects (row-level access).
    """
    @staticmethod
    def for_user(user):
        if user.is_staff:
            return Invoice.objects.select_related("freelancer", "payout_batch")

        if hasattr(user, "freelancer_profile"):  
            return Invoice.objects.filter(
                freelancer=user.freelancer_profile
            ).select_related("payout_batch")

        return Invoice.objects.none()



class InvoiceEarningsSelector:
    """
    Aggregations for freelancers (NOT access control).
    """
    @staticmethod
    def freelancer_summary(freelancer):
        qs = Invoice.objects.filter(freelancer=freelancer, status="issued")

        totals = qs.aggregate(
            total_gross=Sum("total_gross"),
            platform_fee=Sum("platform_fee"),
            total_net=Sum("total_net"),
        )

        return {
            "invoice_count": qs.count(),
            "total_gross": totals["total_gross"] or 0,
            "platform_fee": totals["platform_fee"] or 0,
            "total_net": totals["total_net"] or 0,
        }


class AdminRevenueSelector:
    """
    Aggregations for platform-wide revenue (ADMIN ONLY)
    """
    @staticmethod
    def summary():
        qs = Invoice.objects.filter(status="issued")

        totals = qs.aggregate(
            total_gross=Sum("total_gross"),
            platform_fee=Sum("platform_fee"),
            total_net=Sum("total_net"),
        )

        return {
            "invoice_count": qs.count(),
            "total_gross": totals["total_gross"] or 0,
            "platform_fee": totals["platform_fee"] or 0,
            "total_net_paid_to_freelancers": totals["total_net"] or 0,
        }


class FreelancerMonthlyEarningsSelector:
    """
    Month-wise breakdown of freelancer earnings
    """
    @staticmethod
    def monthly_breakdown(freelancer):
        qs = (
            Invoice.objects
            .filter(freelancer=freelancer, status="issued")
            .annotate(month=TruncMonth("issued_at"))
            .values("month")
            .annotate(
                total_gross=Sum("total_gross"),
                platform_fee=Sum("platform_fee"),
                total_net=Sum("total_net"),
            )
            .order_by("month")
        )

        # convert QuerySet to list for API response
        return list(qs)

