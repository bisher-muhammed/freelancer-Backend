from django.urls import path
from apps.contract.views import (
    AcceptTrackingPolicyView,
    ActiveTrackingPolicyView,
    AdminApproveTerminationView,
    AdminTerminationRequestListView,
    ContractDocumentFolderView,
    ContractDocumentView,
    ContractReviewCreateView,
    FreelancerContractListView,
    ClientContractListView,
    ContractDetailView,
    ContractMessageView,
    ContractTerminateRequestView,
    AdminSettleContractView,
    AdminProcessRefundView,
    FreelancerTestimonialListView
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
    path("tracking/policy/accept/",AcceptTrackingPolicyView.as_view(),name="accept-tracking-policy"),
    path("tracking-policies/active/",ActiveTrackingPolicyView.as_view(),name="active-tracking-policy"),
    path("contracts/<int:pk>/terminate/", ContractTerminateRequestView.as_view(), name="contract-terminate"),
    path("admin/termination-requests/<int:pk>/approve/",AdminApproveTerminationView.as_view(),),
    path("admin/contracts/termination-requests/", AdminTerminationRequestListView.as_view(), name="admin-termination-requests"),
    path("admin/contracts/<int:pk>/settle/", AdminSettleContractView.as_view(), name="admin-settle-contract"),
    path("admin/contracts/<int:pk>/refund-escrow/", AdminProcessRefundView.as_view(), name="admin-process-refund"),
    path("contract-reviews/",ContractReviewCreateView.as_view(),name="contract-review-create",),
    path("freelancers/<int:freelancer_id>/testimonials/",FreelancerTestimonialListView.as_view(),name="freelancer-testimonials",),
    



]

