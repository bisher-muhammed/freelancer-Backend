from amqp import NotFound
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.shortcuts import get_object_or_404
from apps.adminpanel.models import TrackingPolicy
from apps.applications.serializers import MessageSerializer
from apps.applications.models import EscrowPayment, Message
from apps.billing.payouts import EscrowRefundProcessor
from apps.contract.permissions import IsClient, IsContractParty
from apps.contract.serializers import AcceptTrackingPolicySerializer, AdminTerminationRequestSerializer, ContractDocumentSerializer, ContractReviewCreateSerializer, ContractReviewListSerializer, ContractSerializer, ContractDocumentFolderSerializer, TrackingPolicySerializer
from apps.contract.models import Contract, ContractDocument, ContractDocumentFolder, ContractReview, TerminationRequest
from apps.contract.services.termination import settle_contract, terminate_contract




class FreelancerContractListView(generics.ListAPIView):
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role != "freelancer":
            raise PermissionDenied("Only freelancers can view this.")

        freelancer_profile = user.freelancer_profile  # safe now

        return (
            Contract.objects
            .select_related(
                "offer",
                "offer__client",
                "offer__freelancer",
                "offer__proposal",
                "offer__proposal__project",
            )
            .filter(offer__freelancer=freelancer_profile)
            .order_by("-created_at")
        )



class ClientContractListView(generics.ListAPIView):
    serializer_class = ContractSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        if user.role != "client":
            raise PermissionDenied("Only clients can view this.")

        return (
            Contract.objects
            .select_related(
                "offer",
                "offer__client",
                "offer__freelancer",
                "offer__proposal",
                "offer__proposal__project",
            )
            .filter(offer__client=user)
            .order_by("-created_at")
        )

class ContractDetailView(generics.RetrieveAPIView):
    serializer_class = ContractSerializer
    permission_classes = [
        permissions.IsAuthenticated,
        IsContractParty,
    ]

    def get_queryset(self):
        return (
            Contract.objects
            .select_related(
                "offer",
                "offer__client",
                "offer__freelancer",
                "offer__proposal",
                "offer__proposal__project",
            )
        )



class ContractMessageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_contract(self, user, contract_id):
        contract = get_object_or_404(Contract, id=contract_id)

        if user not in [contract.get_client(), contract.get_freelancer_user()]:
            raise PermissionDenied("Not allowed")

        return contract

    def get(self, request, contract_id):
        contract = self.get_contract(request.user, contract_id)
        chat_room = contract.offer.proposal.chat_room

        messages = Message.objects.filter(chat_room=chat_room)
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data)

    def post(self, request, contract_id):
        contract = self.get_contract(request.user, contract_id)
        chat_room = contract.offer.proposal.chat_room

        serializer = MessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            chat_room=chat_room,
            sender=request.user
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ContractDocumentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_contract(self, user, contract_id):
        contract = get_object_or_404(Contract, id=contract_id)

        if user not in [contract.get_client(), contract.get_freelancer_user()]:
            raise PermissionDenied("Not allowed")

        return contract

    def get(self, request, contract_id):
        contract = self.get_contract(request.user, contract_id)

        documents = ContractDocument.objects.filter(contract=contract)
        serializer = ContractDocumentSerializer(
            documents,
            many=True,
            context={"request": request}
        )
        return Response(serializer.data)

    def post(self, request, contract_id):
        contract = self.get_contract(request.user, contract_id)
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"detail": "File is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        
        if uploaded_file.size > 20 * 1024 * 1024:
            return Response(
                {"detail": "File too large (max 20MB)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Prepare data for serializer
        data = request.data.copy()
        
        # Handle folder field - convert to None if empty string
        folder_id = data.get('folder')
        if folder_id == '' or folder_id is None:
            data['folder'] = None
        
        # Create serializer with request context
        serializer = ContractDocumentSerializer(
            data=data,
            context={"request": request}
        )
        
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

        folder = serializer.validated_data.get("folder")
        if folder and folder.contract != contract:
            raise PermissionDenied("Folder does not belong to this contract")

        try:
            document = serializer.save(
                contract=contract,
                uploaded_by=request.user,
                original_name=uploaded_file.name,
                mime_type=uploaded_file.content_type,
                file=uploaded_file,
            )
        except Exception as e:
            return Response(
                {"detail": f"Failed to save document: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            ContractDocumentSerializer(
                document,
                context={"request": request}
            ).data,
            status=status.HTTP_201_CREATED
        )

    def delete(self, request, contract_id, document_id=None):
        contract = self.get_contract(request.user, contract_id)
        
        # If document_id is provided, delete specific document
        if document_id:
            document = get_object_or_404(ContractDocument, id=document_id, contract=contract)
            
            # Check permission - only client can delete
            if request.user != contract.get_client():
                raise PermissionDenied("Only client can delete documents")
            
            document.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        # If no document_id, it's a different endpoint
        raise NotFound("Document ID is required for deletion")


class ContractDocumentFolderView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, contract_id):
        contract = get_object_or_404(Contract, id=contract_id)

        if request.user not in [contract.get_client(), contract.get_freelancer_user()]:
            raise PermissionDenied("Not allowed")

        folders = ContractDocumentFolder.objects.filter(contract=contract)
        serializer = ContractDocumentFolderSerializer(folders, many=True)
        return Response(serializer.data)

    def post(self, request, contract_id):
        contract = get_object_or_404(Contract, id=contract_id)
        name = request.data.get("name")
        if not name:
            return Response(
                {"detail": "Folder name required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        folder, created = ContractDocumentFolder.objects.get_or_create(
            contract=contract,
            name=name,
            defaults={"created_by": request.user}
        )

        return Response(
            {
                "id": folder.id,
                "name": folder.name,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )
    def delete(self, request, contract_id, folder_id):
        contract = get_object_or_404(Contract, id=contract_id)

        if request.user not in [contract.get_client(), contract.get_freelancer_user()]:
            raise PermissionDenied("Not allowed")

        folder = get_object_or_404(ContractDocumentFolder, id=folder_id, contract=contract)

        # Check if folder has documents
        if folder.documents.exists():
            return Response(
                {"detail": "Cannot delete folder with documents."},
                status=status.HTTP_400_BAD_REQUEST
            )

        folder.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    



class AcceptTrackingPolicyView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AcceptTrackingPolicySerializer


    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        consent = serializer.save()

        return Response(
            {
                "message": "Tracking policy accepted successfully.",
                "consent_id": consent.id,
                "policy_version": consent.policy_version
            },
            status=status.HTTP_201_CREATED
        )


class ActiveTrackingPolicyView(generics.RetrieveAPIView):
    """
    Returns the currently active tracking policy.
    Freelancers must read this before accepting tracking.
    """
    serializer_class = TrackingPolicySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        policy = (
            TrackingPolicy.objects
            .filter(is_active=True)
            .order_by("-created_at")
            .first()
        )

        if not policy:
            raise NotFound("No active tracking policy available")

        return policy
    


class ContractTerminateRequestView(APIView):
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk)

        if contract.status != "active":
            return Response(
                {"detail": "Only active contracts can be terminated"},
                status=400
            )

        if hasattr(contract, "termination_request"):
            return Response(
                {"detail": "Termination already requested"},
                status=400
            )

        with transaction.atomic():
            TerminationRequest.objects.create(
                contract=contract,
                requested_by=request.user,
                reason=request.data.get("reason", "")
            )

        return Response(
            {"detail": "Termination request submitted"},
            status=201
        )

class AdminApproveTerminationView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, pk):
        tr = get_object_or_404(
            TerminationRequest.objects.select_related("contract"),
            pk=pk,
            status="pending"
        )

        with transaction.atomic():
            tr.status = "approved"
            tr.reviewed_by = request.user
            tr.reviewed_at = timezone.now()
            tr.save()

            terminate_contract(
                contract=tr.contract,
                actor=request.user
            )

        return Response({"detail": "Contract terminated"}, status=200)



class AdminSettleContractView(APIView):
    """
    POST /admin/contracts/<pk>/settle/
    Computes earned/refundable amounts, writes ledger entries,
    marks billing units as paid, and marks escrow as settled.

    Must be called BEFORE AdminProcessRefundView.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk)

        try:
            escrow = settle_contract(contract=contract, actor=request.user)
        except ValidationError as e:
            return Response({"detail": str(e.message)}, status=400)

        return Response(
            {
                "detail": "Settlement completed (ledger only).",
                "escrow_status": escrow.status,
                "released_amount": str(escrow.released_amount),
                "refunded_amount": str(escrow.refunded_amount),
                "settled_at": escrow.settled_at,
            },
            status=200
        )


# ─────────────────────────────────────────────────────────────────────────────
# Admin: Process Escrow Refund (Stripe + ledger)
# ─────────────────────────────────────────────────────────────────────────────

class AdminProcessRefundView(APIView):
    """
    POST /admin/contracts/<pk>/refund/
    Processes the actual refund to the client via Stripe.
    Requires settle_contract() to have run first (escrow.status == 'settled').
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, pk):
        contract = get_object_or_404(Contract, pk=pk)

        try:
            escrow = contract.offer.payment  # OneToOne reverse lookup
        except EscrowPayment.DoesNotExist:
            return Response({"detail": "No escrow payment found for this contract."}, status=404)

        try:
            EscrowRefundProcessor().process(
                escrow_id=escrow.id,
                actor=request.user
            )
        except ValidationError as e:
            return Response({"detail": str(e.message)}, status=400)

        # Re-fetch to get updated state
        escrow.refresh_from_db()

        return Response(
            {
                "detail": "Refund executed successfully.",
                "escrow_status": escrow.status,
                "refunded_amount": str(escrow.refunded_amount),
                "refunded_at": escrow.refunded_at,
            },
            status=200
        )


class AdminTerminationRequestListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminUser]

    def get(self, request):
        qs = (
            TerminationRequest.objects
            .select_related(
                "contract",
                "contract__offer",
                "contract__offer__client",
                "contract__offer__payment",
                "contract__offer__freelancer__user",
                "requested_by",
            )
            .filter(status__in=["pending", "approved"])
            .order_by("-created_at")
        )

        serializer = AdminTerminationRequestSerializer(qs, many=True)
        return Response(serializer.data, status=200)
    

class ContractReviewCreateView(generics.CreateAPIView):
    """
    Client submits a review after contract completion.
    One review per contract.
    """
    serializer_class = ContractReviewCreateSerializer
    permission_classes = [permissions.IsAuthenticated,IsClient]



class FreelancerTestimonialListView(generics.ListAPIView):
    """
    Public testimonials for a freelancer.
    """
    serializer_class = ContractReviewListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        freelancer_id = self.kwargs["freelancer_id"]

        return (
            ContractReview.objects
            .filter(contract__offer__freelancer_id=freelancer_id)
            .select_related(
                "contract",
                "contract__offer",
                "contract__offer__client",
                "contract__offer__freelancer",
                "contract__offer__freelancer__freelancer_profile",
            )
            .order_by("-created_at")
        )

