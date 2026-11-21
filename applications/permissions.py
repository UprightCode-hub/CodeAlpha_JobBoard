from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission


class IsResumeOwner(BasePermission):
    """Allow a candidate to use their own resume."""

    def has_object_permission(self, request, view, obj):
        return obj.candidate_id == request.user.pk


class IsApplicationJobOwner(BasePermission):
    """Allow the employer that owns an application's job to manage it."""

    def has_object_permission(self, request, view, obj):
        if obj.job.company.owner_id != request.user.pk:
            raise NotFound("The requested resource was not found.")
        return True


class CanViewApplication(BasePermission):
    """Allow an application to be viewed by its candidate or job owner."""

    def has_object_permission(self, request, view, obj):
        user = request.user
        is_candidate = (
            getattr(user, "role", None) == "candidate" and obj.candidate_id == user.pk
        )
        is_owner = (
            getattr(user, "role", None) == "employer"
            and obj.job.company.owner_id == user.pk
        )
        if not (is_candidate or is_owner):
            raise NotFound("The requested resource was not found.")
        return True
