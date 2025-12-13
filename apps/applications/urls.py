from django.urls import path
from .views import ProjectDetailView, ProposalCreateView,MyProposals

urlpatterns = [
    path('project/<int:id>/', ProjectDetailView.as_view(), name='project-detail'),
    path('proposal/apply/', ProposalCreateView.as_view(), name='proposal-apply'),
    path('my-proposals/', MyProposals.as_view(), name='my-proposals'),
]

