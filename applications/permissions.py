from rest_framework.permissions import BasePermission


class IsCandidate(BasePermission):
    """Allow access to authenticated candidate accounts."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "candidate"
        )


class IsEmployer(BasePermission):
    """Allow access to authenticated employer accounts."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == "employer"
        )
