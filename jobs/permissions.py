from rest_framework.permissions import BasePermission


class IsEmployer(BasePermission):
    """Allow access to authenticated employer accounts."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "employer"
        )


class IsJobOwner(BasePermission):
    """Allow an employer to access jobs owned by their company."""

    def has_object_permission(self, request, view, obj):
        return obj.company.owner_id == request.user.pk
