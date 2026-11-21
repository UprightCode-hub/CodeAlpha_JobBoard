from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from accounts.permissions import IsEmployer


class IsJobOwner(BasePermission):
    """Allow an employer to access jobs owned by their company."""

    def has_object_permission(self, request, view, obj):
        return obj.company.owner_id == request.user.pk


class IsOpenJobOrOwner(BasePermission):
    """Allow open jobs to everyone and closed jobs only to their employer."""

    def has_object_permission(self, request, view, obj):
        if obj.is_open:
            return True
        if IsEmployer().has_permission(
            request, view
        ) and IsJobOwner().has_object_permission(request, view, obj):
            return True
        raise NotFound("The requested resource was not found.")
