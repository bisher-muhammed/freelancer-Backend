from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.applications import views
from apps.applications.video_token import ZegoTokenView, MeetingJoinTokenView
from apps.applications.views import (
    ClientOfferDetailView,
    ClientOfferListView,
    FreelancerOfferDetailView,
    FreelancerOfferListView,
    FreelancerProposalDetailView,
    MeetingViewSet,
    MyProposals,
    OfferAcceptView,
    OfferCreateView,
    OfferRejectView,
    ProjectDetailView,
    ProposalCreateView,
    SavedProjectListView,
    ToggleSaveProjectView,
    CreateEscrowCheckoutSession
)

router = DefaultRouter()
router.register(r'meetings', MeetingViewSet, basename='meeting')

urlpatterns = [
    path('', include(router.urls)),

    path('project/<int:id>/', ProjectDetailView.as_view(), name='project-detail'),
    path('project/save-toggle/', ToggleSaveProjectView.as_view()),
    path('project/saved/', SavedProjectListView.as_view()),
    path('proposal/apply/', ProposalCreateView.as_view(), name='proposal-apply'),
    path('my-proposals/', MyProposals.as_view(), name='my-proposals'),
    path('freelancer/my-proposals/<int:id>/', FreelancerProposalDetailView.as_view(), name="freelancer-proposal-detail"),

    # --- Chat & Messaging ---
    path('chat-rooms/get-or-create/', views.ChatRoomGetOrCreateView.as_view()),
    path('chat-rooms/client/', views.ClientChatRoomListView.as_view()),
    path('chat-rooms/freelancer/', views.FreelancerChatRoomListView.as_view()),
    path('chat/<int:chat_id>/messages/', views.MessageListView.as_view()),
    path('chat/<int:chat_id>/mark-read/', views.MarkChatAsReadView.as_view()),

    # --- Video & Meetings ---
    path('video/zego-token/', ZegoTokenView.as_view()),
    path('meeting/zego-token/', MeetingJoinTokenView.as_view()),

    # --- Offers (General) ---
    path('offers/create/', OfferCreateView.as_view(), name="offer-create"),
    path('offers/<int:id>/accept/', OfferAcceptView.as_view(), name="offer-accept"),
    path('offers/<int:id>/reject/', OfferRejectView.as_view(), name="offer-reject"),

    # --- Offers (Client Specific) ---
    path('offers/client/', ClientOfferListView.as_view(), name="client-offer-list"),
    path('offers/client/<int:id>/', ClientOfferDetailView.as_view(), name="client-offer-detail"),

    # --- Offers (Freelancer Specific) ---
    path('offers/freelancer/', FreelancerOfferListView.as_view(), name="freelancer-offer-list"),
    path('offers/freelancer/<int:id>/', FreelancerOfferDetailView.as_view(), name="freelancer-offer-detail"),
    path("client/create-checkout-payment/",CreateEscrowCheckoutSession.as_view()),
    path("offers/client/", ClientOfferListView.as_view(), name="client-offer-list"),
]
