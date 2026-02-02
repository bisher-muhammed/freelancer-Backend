from django.urls import path
from apps.contract.views import (
    AcceptTrackingPolicyView,
    ActiveTrackingPolicyView,
    ContractDocumentFolderView,
    ContractDocumentView,
    FreelancerContractListView,
    ClientContractListView,
    ContractDetailView,
    ContractMessageView,
)


urlpatterns = [
    path('freelancer/contracts/', FreelancerContractListView.as_view(), name='freelancer-contracts'),
    path('client/contracts/', ClientContractListView.as_view(), name='client-contracts'),
    path('contracts/<int:pk>/', ContractDetailView.as_view(), name='contract-detail'),
    path("contracts/<int:contract_id>/messages/", ContractMessageView.as_view()),
    path("contracts/<int:contract_id>/documents/", ContractDocumentView.as_view()),
    path("contracts/<int:contract_id>/documents/<int:document_id>/", ContractDocumentView.as_view()),
    path("contracts/<int:contract_id>/documents-folders/", ContractDocumentFolderView.as_view()),
    path("contracts/<int:contract_id>/documents-folders/<int:folder_id>/", ContractDocumentFolderView.as_view()),
    path( "tracker/policy/accept/",AcceptTrackingPolicyView.as_view(),name="accept-tracking-policy"),
    path("tracking-policies/active/",ActiveTrackingPolicyView.as_view(),name="active-tracking-policy")


]
