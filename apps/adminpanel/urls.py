from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import AdminUserList, AdminSubscriptionPlanViewSet,toggle_block ,admin_get_freelancer, admin_verify_freelancer

router = DefaultRouter()
router.register(
    r'subscription-plans',
    AdminSubscriptionPlanViewSet,
    basename='admin-subscription-plans'
)

urlpatterns = [
    path("users/", AdminUserList.as_view(), name="admin-users"),

    path('toggle_block/',toggle_block,name='toggle-block'),

    path('freelancers/<int:user_id>/', admin_get_freelancer, name='admin-get-freelancer'),
    path('freelancers/<int:user_id>/verify/', admin_verify_freelancer, name='admin-verify-freelancer'),

    # Add this so the router actually works
    path("", include(router.urls)),
]
