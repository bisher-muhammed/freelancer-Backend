from rest_framework.permissions import BasePermission

class IsContractParty(BasePermission):
    def has_object_permission(self, request, view, obj):
        return (
            obj.offer.client == request.user or
            obj.offer.freelancer.user == request.user  # fix here
        )