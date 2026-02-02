from decimal import Decimal

from apps.billing.selectors import AdminRevenueSelector, FreelancerMonthlyEarningsSelector, InvoiceAccessSelector, InvoiceEarningsSelector
from apps.billing.services import InvoiceService
PLATFORM_FEE_PERCENT = Decimal("10.00")
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.generics import RetrieveAPIView, ListAPIView

from apps.billing.payouts import MockPayoutProcessor

from .models import BillingUnit, PayoutBatch
from .serializers import (
    BillingUnitListSerializer,
    BillingUnitReviewSerializer,
    InvoiceSerializer,
    PayoutConfirmSerializer,
    PayoutPreviewSerializer,
)

from apps.freelancer.models import FreelancerProfile

User = get_user_model()



class AdminBillingUnitListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        status_param = request.query_params.get("status")

        qs = BillingUnit.objects.select_related(
            "contract", "freelancer", "session"
        ).order_by("-created_at")

        if status_param:
            qs = qs.filter(status=status_param)

        return Response(
            BillingUnitListSerializer(qs, many=True).data
        )






class BillingUnitReviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, billing_id):
        billing = get_object_or_404(BillingUnit, id=billing_id)

        serializer = BillingUnitReviewSerializer(
            instance=billing,
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({"status": billing.status})





class FreelancerBillingUnitListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = BillingUnit.objects.filter(
            freelancer=request.user
        ).select_related("contract", "session")

        return Response(
            BillingUnitListSerializer(qs, many=True).data
        )



class AdminPayoutPreviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        freelancer_id = request.data.get("freelancer_id")
        if not freelancer_id:
            return Response({"detail": "freelancer_id is required"}, status=400)

        freelancer = get_object_or_404(FreelancerProfile, id=freelancer_id)
        preview = PayoutPreviewSerializer.build(freelancer=freelancer)
        return Response(preview.data)

        





class PayoutConfirmView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        serializer = PayoutConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payout = serializer.save()

        # simulate immediate payout
        processor = MockPayoutProcessor()
        processor.process(payout)
        InvoiceService.create_from_payout(payout)

        return Response(
            {
                "payout_id": payout.id,
                "status": payout.status,
                "total_net": payout.total_net,
            },
            status=status.HTTP_201_CREATED,
        )
       





class AdminBillingUnitDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAdminUser]
    serializer_class = BillingUnitListSerializer
    
    def get_queryset(self):
        return BillingUnit.objects.select_related(
            "contract", "freelancer", "session"
        )
    
    def get_object(self):
        billing_id = self.kwargs.get('billing_id')
        return get_object_or_404(self.get_queryset(), id=billing_id)




class InvoiceListView(ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return InvoiceAccessSelector.for_user(self.request.user)
    


class InvoiceDetailView(RetrieveAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        return InvoiceAccessSelector.for_user(self.request.user)


class FreelancerEarningsSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, "freelancer_profile"): 
            return Response(
                {"detail": "Only freelancers can access earnings summary"},
                status=403,
            )

        data = InvoiceEarningsSelector.freelancer_summary(
            request.user.freelancer_profile  # ✅ correct
        )
        return Response(data)




class AdminRevenueSummaryView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        data = AdminRevenueSelector.summary()
        return Response(data)



class FreelancerMonthlyEarningsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not hasattr(request.user, "freelancerprofile"):
            return Response(
                {"detail": "Only freelancers can access this"},
                status=403,
            )

        data = FreelancerMonthlyEarningsSelector.monthly_breakdown(
            request.user.freelancerprofile
        )
        return Response(data)
