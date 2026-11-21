from rest_framework.permissions import BasePermission


class IsRole(BasePermission):
    """Allow authenticated users with the configured account role."""

    role: str | None = None

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) == self.role
        )


class IsCandidate(IsRole):
    """Allow access to authenticated candidate accounts."""

    role = "candidate"


class IsEmployer(IsRole):
    """Allow access to authenticated employer accounts."""

    role = "employer"
