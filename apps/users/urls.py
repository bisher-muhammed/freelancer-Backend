from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
CreateCheckoutSession,
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
BrowseFreelancers
)


# Router for profile endpoints

profile_router = DefaultRouter()
profile_router.register("profile", ClientProfileViewSet, basename="client-profile")

# Router for project endpoints

project_router = DefaultRouter()
project_router.register("projects", ProjectViewSet, basename="projects")

urlpatterns = [
# Authentication & registration
path('send-otp/', SendOTPView.as_view(), name='send-otp'),
path('register/', RegisterView.as_view(), name='register'),
path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
path('login/', LoginView.as_view(), name='login'),
path('google-login/', google_login, name='google-login'),

# Password reset  
path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),  
path('verify-reset-otp/', VerifyPasswordResetOTPView.as_view(), name='verify-reset-otp'),  
path('reset-password/', ResetPasswordView.as_view(), name='reset-password'), 


path('subscriptions/', SubscriptionPlanListView.as_view(), name='subscription-plans'),
path('user-subscription/', UserSubscriptionViewSet.as_view(), name='user-subscription'),

path("create-checkout-session/",CreateCheckoutSession.as_view(), name="create-checkout-session"),
path("stripe-webhook/", stripe_webhook, name="stripe-webhook"),


# freelancers
path("freelancers/", BrowseFreelancers.as_view(),name = "freelancers"),






# Profile routes  
path('', include(profile_router.urls)),  

# Project routes  
path('', include(project_router.urls)),  


]

