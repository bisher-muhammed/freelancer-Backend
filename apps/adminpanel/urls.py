from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdminMeetingViewSet, AdminProjectDetailView, AdminProjectListView, AdminUserList, AdminSubscriptionPlanViewSet, TrackingPolicyCreateView, TrackingPolicyListView,toggle_block ,admin_get_freelancer, admin_verify_freelancer,AdminProjectScoringConfigViewSet

router = DefaultRouter()
router.register(
    r'subscription-plans',
    AdminSubscriptionPlanViewSet,
    basename='admin-subscription-plans'
)

# Remove the trailing slash from the pattern
router.register(r'project-scoring-config', AdminProjectScoringConfigViewSet, basename='admin-proposal-score')
router.register(
    r"admin-meetings",
    AdminMeetingViewSet,
    basename="admin-meetings"
)

urlpatterns = [
    path("users/", AdminUserList.as_view(), name="admin-users"),
    path('toggle_block/',toggle_block,name='toggle-block'),
    path('freelancers/<int:user_id>/', admin_get_freelancer, name='admin-get-freelancer'),
    path('freelancers/<int:user_id>/verify/', admin_verify_freelancer, name='admin-verify-freelancer'),
    path("admin-projects/", AdminProjectListView.as_view()),
    path("admin-projects/<int:pk>/", AdminProjectDetailView.as_view()),
    path("admin-tracking-policy/create",TrackingPolicyCreateView.as_view()),
    path("admin-tracking-policy/list",TrackingPolicyListView.as_view()),
    


    
    # This includes the router URLs
    path("", include(router.urls)),
]
