from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone

from apps.applications.models import ChatRoom, Meeting
from apps.applications.utils.throttles import ZegoTokenRateThrottle
from apps.token04.zego_token import generate_zego_token


class ZegoTokenView(APIView):
    """
    Generates a Zego token for casual chat rooms.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ZegoTokenRateThrottle]
    MAX_TOKEN_TTL = 1800  # 30 minutes hard cap

    def post(self, request):
        user = request.user
        chat_room_id = request.data.get("chat_room_id")

        if not chat_room_id:
            return Response({"error": "chat_room_id required"}, status=400)

        chat_room = get_object_or_404(
            ChatRoom.objects.select_related("client", "freelancer"),
            id=chat_room_id,
            is_active=True
        )

        if user not in (chat_room.client, chat_room.freelancer):
            return Response({"error": "Forbidden"}, status=403)

        if not settings.APPID or not settings.ZEGO_SERVER_URL:
            return Response({"error": "Zego not configured"}, status=500)

        token = generate_zego_token(
            user_id=f"user_{user.id}",
            room_id=f"chatroom_{chat_room.id}",
            expire_seconds=self.MAX_TOKEN_TTL
        )

        return Response({
            "app_id": settings.APPID,
            "server": settings.ZEGO_SERVER_URL,
            "zego_token": token,
            "room_id": f"chatroom_{chat_room.id}",
            "user_id": f"user_{user.id}",
        }, status=200)


class MeetingJoinTokenView(APIView):
    """
    Generates a Zego token for scheduled meetings.
    Handles cooldown, join buffers, and TTL caps.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ZegoTokenRateThrottle]
    MAX_TOKEN_TTL = 3600  # 1 hour hard cap

    def post(self, request):
        user = request.user
        meeting_id = request.data.get("meeting_id")

        if not meeting_id:
            return Response({"error": "meeting_id required"}, status=400)

        meeting = get_object_or_404(
            Meeting.objects.select_related("chat_room", "proposal__project"),
            id=meeting_id,
            status="scheduled"
        )

        # Participant check
        if user not in (meeting.client, meeting.freelancer):
            return Response({"error": "Forbidden"}, status=403)

        now = timezone.now()

        # Join time buffers
        if now < meeting.start_time - meeting.JOIN_EARLY_BUFFER:
            return Response({"error": "Meeting not open yet"}, status=403)
        if now > meeting.end_time + meeting.JOIN_LATE_BUFFER:
            return Response({"error": "Meeting has ended"}, status=403)

        # Token cooldown
        if not meeting.can_issue_token():
            return Response({"error": "Token requested too frequently"}, status=429)
        meeting.mark_token_issued()

        expire_seconds = min(meeting.remaining_seconds(), self.MAX_TOKEN_TTL)
        if expire_seconds <= 0:
            return Response({"error": "Meeting expired"}, status=403)

        if not settings.APPID or not settings.ZEGO_SERVER_URL:
            return Response({"error": "Zego not configured"}, status=500)

        token = generate_zego_token(
            user_id=f"user_{user.id}",
            room_id=f"meeting_{meeting.id}",
            expire_seconds=expire_seconds
        )

        role = "host" if user == meeting.client else "participant"

        return Response({
            "app_id": settings.APPID,
            "server": settings.ZEGO_SERVER_URL,
            "zego_token": token,
            "room_id": f"meeting_{meeting.id}",
            "user_id": f"user_{user.id}",
            "meeting_id": meeting.id,
            "expires_in": expire_seconds,
            "role": role,
        }, status=200)

