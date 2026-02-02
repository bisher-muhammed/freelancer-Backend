from amqp import NotFound
from django.shortcuts import render
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from apps.adminpanel.models import TrackingPolicy
from apps.applications.serializers import MessageSerializer
from apps.applications.models import Message
from apps.contract.permissions import IsContractParty
from apps.contract.serializers import AcceptTrackingPolicySerializer, ContractDocumentSerializer, ContractSerializer, ContractDocumentFolderSerializer, TrackingPolicySerializer
from apps.contract.models import Contract, ContractDocument, ContractDocumentFolder
from apps.freelancer.models import FreelancerProfile




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

        # 🔐 FILE SIZE LIMIT (20MB)
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