from rest_framework.routers import DefaultRouter
from .views import NotificationViewSet, AdminActivityListView, ClientActivityListView
from django.urls import path


urlpatterns = [
    path("admin/activity/", AdminActivityListView.as_view(), name="admin-activity"),
    path("client/activity/", ClientActivityListView.as_view(), name="client-activity"),
]


router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notifications")


urlpatterns += router.urls