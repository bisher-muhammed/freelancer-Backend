from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
ClientRecentProjectsView,
ClientStatisticsView,
ClientProposalStatusUpdateView,
CompletedProjectsView,
CreateCheckoutSession,
FreelancerCompletedProjectsView,
SendOTPView,
RegisterView,
SubscriptionPlanListView,
VerifyOTPView,
LoginView,
google_login,
ForgotPasswordView,
VerifyPasswordResetOTPView,
ResetPasswordView,
ClientProfileViewSet,
ProjectViewSet,
CreateCheckoutSession,
stripe_webhook,
UserSubscriptionViewSet,
BrowseFreelancers,
ClientProposalListView,
ClientProposalStatusUpdateView ,
FreelancerProfileDetailView,
ClientProposalDetailView
)



profile_router = DefaultRouter()
profile_router.register("profile", ClientProfileViewSet, basename="client-profile")
project_router = DefaultRouter()
project_router.register("projects", ProjectViewSet, basename="projects")
urlpatterns = [
path('send-otp/', SendOTPView.as_view(), name='send-otp'),
path('register/', RegisterView.as_view(), name='register'),
path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
path('login/', LoginView.as_view(), name='login'),
path('google-login/', google_login, name='google-login'),
path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),  
path('verify-reset-otp/', VerifyPasswordResetOTPView.as_view(), name='verify-reset-otp'),  
path('reset-password/', ResetPasswordView.as_view(), name='reset-password'), 
path('subscriptions/', SubscriptionPlanListView.as_view(), name='subscription-plans'),
path('user-subscription/', UserSubscriptionViewSet.as_view(), name='user-subscription'),
path("create-checkout-session/",CreateCheckoutSession.as_view(), name="create-checkout-session"),
path("stripe-webhook/", stripe_webhook, name="stripe-webhook"),
path("freelancers/", BrowseFreelancers.as_view(),name = "freelancers"),
path('freelancer-profile/<int:user_id>/',FreelancerProfileDetailView.as_view(),name='freelancer-profile'),
path("proposals/",ClientProposalListView.as_view(),name="client-proposal-list"),
path ("proposals/<int:pk>/status/",ClientProposalStatusUpdateView.as_view(),name="client-proposal-status-update"),
path('proposals/<int:pk>/', ClientProposalDetailView.as_view(), name='client-proposal-detail'),
path("client/statistics/", ClientStatisticsView.as_view(), name="client-statistics"),
path("client/recent-projects/", ClientRecentProjectsView.as_view(), name="client-recent-projects"),
path("client/completed-projects/",CompletedProjectsView.as_view(),name="client-completed-projects",),
path("freelancer/completed-projects/",FreelancerCompletedProjectsView.as_view(),name="freelancer-completed-projects",),

  
path('', include(profile_router.urls)),  

path('', include(project_router.urls)),  


]

