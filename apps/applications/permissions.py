# applications/permissions.py
from rest_framework.permissions import BasePermission

class IsChatParticipant(BasePermission):
    """
    Allows access only to chat participants (client or freelancer).
    """
    def has_object_permission(self, request, view, obj):
        return request.user in [obj.client, obj.freelancer]


class IsClientOwnerOfProposal(BasePermission):
    """
    Allows creation of chat room only if the request.user
    is the client who owns the proposal's project.
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        proposal_id = request.data.get("proposal")
        if not proposal_id:
            return False

        from apps.applications.models import Proposal
        try:
            proposal = Proposal.objects.get(id=proposal_id)
        except Proposal.DoesNotExist:
            return False

        return proposal.project.client == request.user



class IsClientParticipant(BasePermission):
    """
    Client of the meeting only.
    """
    def has_object_permission(self, request, view, obj):
        return obj.chat_room.client == request.user



class IsClient(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "client"
        )


class IsFreelancer(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.role == "freelancer"
        )