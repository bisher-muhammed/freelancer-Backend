from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework import status, generics, serializers
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone

from apps.billing.models import BillingUnit
from apps.billing.serializers import BillingUnitListSerializer
from apps.tracking.models import ActivityLog, Device, TimeBlock, TimeBlockExplanation, WorkSession
from .serializers import (
    ActivityLogSerializer,
    FreelancerSessionListSerializer,
    ScreenshotUploadSerializer,
    TimeBlockExplanationCreateSerializer,
    TimeBlockExplanationReviewSerializer,
    TimeBlockFlagUpdateSerializer,
    TimeBlockSerializer,
    WorkSessionStartSerializer,
    WorkSessionPauseSerializer,
    WorkSessionResumeSerializer,
    WorkSessionStopSerializer,
    WorkSessionDetailSerializer,
    IdleFlushSerializer,
)


# ===============================
# Start Work Session
# ===============================
class StartSessionView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkSessionStartSerializer

    @transaction.atomic
    def post(self, request):
        existing = (
            WorkSession.objects
            .select_for_update()
            .filter(user=request.user, ended_at__isnull=True)
            .first()
        )

        if existing:
            return Response(
                {
                    "session_id": existing.id,
                    "status": "already_running",
                    "started_at": existing.started_at,
                },
                status=status.HTTP_200_OK,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = serializer.save()

        return Response(
            {
                "session_id": session.id,
                "status": "started",
                "started_at": session.started_at,
            },
            status=status.HTTP_201_CREATED,
        )


# ===============================
# Pause Session
# ===============================
class PauseSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        serializer = WorkSessionPauseSerializer(
            data={"session_id": session_id, **request.data},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "paused"}, status=status.HTTP_200_OK)


# ===============================
# Resume Session
# ===============================
class ResumeSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        serializer = WorkSessionResumeSerializer(
            data={"session_id": session_id},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "resumed"}, status=status.HTTP_200_OK)


# ===============================
# Stop Session
# ===============================
class StopSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        serializer = WorkSessionStopSerializer(
            data={"session_id": session_id, **request.data},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        session = serializer.save()
        return Response(
            {
                "status": "stopped",
                "session_id": session.id,
                "total_seconds": session.total_seconds,
                "ended_at": session.ended_at,
            },
            status=status.HTTP_200_OK,
        )


# ===============================
# Upload Screenshot
# ===============================
class UploadScreenshotView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = ScreenshotUploadSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        screenshot = serializer.save()

        return Response(
            {
                "screenshot_id": screenshot.id,
                "taken_at_client": screenshot.taken_at_client,
                "uploaded_at": screenshot.uploaded_at,
            },
            status=status.HTTP_201_CREATED,
        )


# ===============================
# Device Check or Create
# ===============================
class DeviceCheckOrCreateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        device, created = Device.objects.get_or_create(
            device_id=data["device_id"],
            freelancer=request.user,
            defaults={
                "device_name": data.get("device_name", ""),
                "os_name": data.get("os_name", ""),
                "os_version": data.get("os_version", ""),
            },
        )
        return Response({"status": "ok", "created": created})


# ===============================
# Active Session
# ===============================
class ActiveSessionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session = (
            WorkSession.objects
            .filter(user=request.user, ended_at__isnull=True)
            .first()
        )

        if not session:
            return Response({"status": "no_active_session"})

        open_block = session.time_blocks.filter(
            ended_at__isnull=True
        ).first()

        return Response({
            "status": "running",
            "session_id": session.id,
            "is_paused": open_block is None,
            "live_total_seconds": session.live_total_seconds,
            "total_seconds": session.total_seconds,
        })



# ===============================
# Freelancer Session Timeline
# ===============================
class FreelancerSessionTimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(
            WorkSession.objects.prefetch_related(
                "time_blocks__windows__screenshots"
            ),
            id=session_id,
            user=request.user,
        )
        serializer = WorkSessionDetailSerializer(session)
        return Response(serializer.data)


# ===============================
# Freelancer Session List
# ===============================
class FreelancerSessionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        sessions = WorkSession.objects.filter(user=request.user)
        serializer = FreelancerSessionListSerializer(sessions, many=True)
        return Response(serializer.data)


# ===============================
# Idle Flush
# ===============================
class IdleFlushView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        serializer = IdleFlushSerializer(
            data={"session_id": session_id, **request.data},
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"status": "idle_flushed"})


# ===============================
# Admin Views
# ===============================
class AdminWorkSessionListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        sessions = WorkSession.objects.all().order_by("-started_at")
        serializer = WorkSessionDetailSerializer(sessions, many=True)
        return Response(serializer.data)


class AdminWorkSessionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request, session_id):
        session = get_object_or_404(WorkSession, id=session_id)
        session_serializer = WorkSessionDetailSerializer(session)

        billing_units = BillingUnit.objects.filter(session=session)
        billing_serializer = BillingUnitListSerializer(billing_units, many=True)

        return Response(
            {
                "session": session_serializer.data,
                "billing_units": billing_serializer.data,
            }
        )



class TimeBlockExplanationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TimeBlockExplanationCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        explanation = serializer.save()

        return Response(
            TimeBlockExplanationReviewSerializer(explanation).data,
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        user = request.user

        queryset = TimeBlockExplanation.objects.select_related(
            "block", "freelancer"
        )

        # ----------------------------
        # ADMIN ACCESS
        # ----------------------------
        if user.is_staff:
            flagged = request.query_params.get("flagged")
            freelancer_id = request.query_params.get("freelancer_id")

            if flagged is not None:
                queryset = queryset.filter(
                    flag=str(flagged).lower() in ("true", "1", "yes")
                )

            if freelancer_id:
                queryset = queryset.filter(freelancer_id=freelancer_id)

        # ----------------------------
        # FREELANCER ACCESS
        # ----------------------------
        else:
            queryset = queryset.filter(freelancer__user=user)

        serializer = TimeBlockExplanationReviewSerializer(
            queryset.order_by("-created_at"),
            many=True,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)



class AdminTimeBlockFlagUpdateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, id):
        timeblock = get_object_or_404(TimeBlock, id=id)

        serializer = TimeBlockFlagUpdateSerializer(
            timeblock,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            TimeBlockSerializer(timeblock).data,
            status=status.HTTP_200_OK,
        )




class AdminExplanationReviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def patch(self, request, block_id):
        explanation = get_object_or_404(
            TimeBlockExplanation, 
            block_id=block_id
        )
        
        serializer = TimeBlockExplanationReviewSerializer(
            explanation,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return Response(
            TimeBlockExplanationReviewSerializer(explanation).data,
            status=status.HTTP_200_OK,
        )



class FreelancerActivityLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        freelancer = request.user.freelancer_profile

        qs = ActivityLog.objects.filter(
            freelancer=freelancer
        ).select_related(
            "freelancer__user",
            "session"
        ).order_by("-created_at")[:100]

        return Response(ActivityLogSerializer(qs, many=True).data)


class AdminActivityLogView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        logs = (
            ActivityLog.objects.all()
            .select_related("freelancer__user", "session")
            .order_by("-created_at")[:300]
        )

        serializer = ActivityLogSerializer(logs, many=True)
        return Response(serializer.data)