from datetime import timedelta

from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from jobs.models import Job

from .models import Application, Notification, Resume
from .permissions import IsCandidate, IsEmployer
from .serializers import (
    ApplicationSerializer,
    ApplySerializer,
    NotificationSerializer,
    ResumeSerializer,
    ResumeUploadSerializer,
    StatusSerializer,
)


def coded_error(code, message):
    return Response(
        {"error": {"code": code, "message": message}},
        status=status.HTTP_400_BAD_REQUEST,
    )


class ResumeListCreateView(APIView):
    permission_classes = (IsAuthenticated, IsCandidate)

    def get(self, request):
        queryset = Resume.objects.filter(candidate=request.user).order_by(
            "-uploaded_at", "-id"
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ResumeSerializer(page, many=True).data)

    def post(self, request):
        serializer = ResumeUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume = serializer.save(candidate=request.user)
        return Response(ResumeSerializer(resume).data, status=status.HTTP_201_CREATED)


class ApplicationListCreateView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        queryset = Application.objects.select_related(
            "job", "job__company", "candidate", "resume"
        )
        if getattr(request.user, "role", None) == "candidate":
            queryset = queryset.filter(candidate=request.user)
        elif getattr(request.user, "role", None) == "employer":
            queryset = queryset.filter(job__company__owner=request.user)
        else:
            queryset = queryset.none()
        queryset = queryset.order_by("-applied_at", "-id")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ApplicationSerializer(page, many=True).data
        )

    def post(self, request):
        if getattr(request.user, "role", None) != "candidate":
            return Response(
                {"error": {"code": "permission_denied", "message": "You do not have permission to perform this action."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        try:
            job = Job.objects.select_related("company").get(pk=values["job"])
        except Job.DoesNotExist:
            raise ValidationError({"job": "The selected job does not exist."})
        try:
            resume = Resume.objects.get(pk=values["resume"])
        except Resume.DoesNotExist:
            raise ValidationError({"resume": "The selected resume does not exist."})

        if not job.is_open:
            return coded_error("job_closed", "This job is closed and cannot accept applications.")
        if resume.candidate_id != request.user.pk:
            return coded_error("invalid_resume", "The selected resume does not belong to you.")
        if Application.objects.filter(candidate=request.user, job=job).exists():
            return coded_error("duplicate_application", "You have already applied for this job.")

        try:
            with transaction.atomic():
                application = Application.objects.create(
                    candidate=request.user, job=job, resume=resume
                )
                Notification.objects.create(
                    recipient=job.company.owner,
                    application=application,
                    message=f"{request.user.username} applied for {job.title}",
                )
        except IntegrityError:
            if Application.objects.filter(candidate=request.user, job=job).first() is not None:
                return coded_error(
                    "duplicate_application", "You have already applied for this job."
                )
            raise

        application = Application.objects.select_related(
            "job", "job__company", "candidate", "resume"
        ).get(pk=application.pk)
        return Response(
            ApplicationSerializer(application).data, status=status.HTTP_201_CREATED
        )


class ApplicationDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request, pk):
        application = get_object_or_404(
            Application.objects.select_related("job", "job__company", "candidate", "resume"),
            pk=pk,
        )
        is_candidate = (
            getattr(request.user, "role", None) == "candidate"
            and application.candidate_id == request.user.pk
        )
        is_owner = (
            getattr(request.user, "role", None) == "employer"
            and application.job.company.owner_id == request.user.pk
        )
        if not (is_candidate or is_owner):
            raise NotFound("The requested resource was not found.")
        return Response(ApplicationSerializer(application).data)


class ApplicationStatusView(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, pk):
        if getattr(request.user, "role", None) == "candidate":
            return Response(
                {"error": {"code": "permission_denied", "message": "You do not have permission to perform this action."}},
                status=status.HTTP_403_FORBIDDEN,
            )
        if getattr(request.user, "role", None) != "employer":
            return Response(
                {"error": {"code": "permission_denied", "message": "You do not have permission to perform this action."}},
                status=status.HTTP_403_FORBIDDEN,
            )

        application = get_object_or_404(
            Application.objects.select_related("job", "job__company", "candidate", "resume"),
            pk=pk,
        )
        if application.job.company.owner_id != request.user.pk:
            raise NotFound("The requested resource was not found.")

        serializer = StatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target = serializer.validated_data["status"]
        allowed = {
            "applied": {"reviewing", "rejected"},
            "reviewing": {"shortlisted", "rejected"},
            "shortlisted": {"hired", "rejected"},
            "hired": set(),
            "rejected": set(),
        }
        if target not in allowed.get(application.status, set()):
            return coded_error("invalid_transition", "This status transition is not allowed.")

        application.status = target
        application.updated_at = max(
            timezone.now(), application.updated_at + timedelta(microseconds=1)
        )
        application.save(update_fields=("status", "updated_at"))
        return Response(ApplicationSerializer(application).data)


class NotificationListView(APIView):
    permission_classes = (IsAuthenticated, IsEmployer)

    def get(self, request):
        queryset = Notification.objects.filter(recipient=request.user).select_related(
            "application"
        ).order_by("-created_at", "-id")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            NotificationSerializer(page, many=True).data
        )
