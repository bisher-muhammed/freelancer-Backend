from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAdminUser


from .models import ActivityLog, Notification
from .serializers import AdminActivitySerializer, ClientActivitySerializer, NotificationSerializer


class NotificationViewSet(ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(
            recipient=self.request.user
        )

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.save(update_fields=["is_read"])

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    def read_all(self, request):
        Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).update(is_read=True)

        return Response(status=status.HTTP_204_NO_CONTENT)



class AdminActivityListView(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = AdminActivitySerializer

    def get_queryset(self):
        return ActivityLog.objects.all()[:5] 


class ClientActivityListView(ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        activities = ActivityLog.objects.filter(
            metadata__client_id=user.id
        ).order_by("-created_at")[:5]

        serializer = ClientActivitySerializer(activities, many=True)
        return Response(serializer.data)