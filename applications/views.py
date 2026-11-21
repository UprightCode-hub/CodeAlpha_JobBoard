from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCandidate, IsEmployer
from config.exceptions import CodedAPIException
from jobs.models import Job

from .models import Application, Notification, Resume
from .permissions import (
    CanViewApplication,
    IsApplicationJobOwner,
    IsResumeOwner,
)
from .serializers import (
    ApplicationSerializer,
    ApplySerializer,
    NotificationSerializer,
    ResumeSerializer,
    ResumeUploadSerializer,
    StatusSerializer,
)

PAGE_PARAMETER = OpenApiParameter(
    "page",
    OpenApiTypes.INT,
    OpenApiParameter.QUERY,
)
RESUME_LIST_RESPONSE = inline_serializer(
    name="ResumeListResponse",
    fields={
        "count": serializers.IntegerField(),
        "next": serializers.URLField(allow_null=True),
        "previous": serializers.URLField(allow_null=True),
        "results": ResumeSerializer(many=True),
    },
)
APPLICATION_LIST_RESPONSE = inline_serializer(
    name="ApplicationListResponse",
    fields={
        "count": serializers.IntegerField(),
        "next": serializers.URLField(allow_null=True),
        "previous": serializers.URLField(allow_null=True),
        "results": ApplicationSerializer(many=True),
    },
)
NOTIFICATION_LIST_RESPONSE = inline_serializer(
    name="NotificationListResponse",
    fields={
        "count": serializers.IntegerField(),
        "next": serializers.URLField(allow_null=True),
        "previous": serializers.URLField(allow_null=True),
        "results": NotificationSerializer(many=True),
    },
)
RESUME_UPLOAD_REQUEST = inline_serializer(
    name="ResumeUploadRequest",
    fields={
        "title": serializers.CharField(),
        "file": serializers.FileField(),
    },
)
APPLY_REQUEST = inline_serializer(
    name="ApplyRequest",
    fields={
        "job": serializers.IntegerField(),
        "resume": serializers.IntegerField(),
    },
)
STATUS_REQUEST = inline_serializer(
    name="ApplicationStatusRequest",
    fields={
        "status": serializers.ChoiceField(
            choices=("applied", "reviewing", "shortlisted", "rejected", "hired")
        ),
    },
)


class ResumeListCreateView(APIView):
    """List the candidate's resumes or upload a new resume."""

    permission_classes = (IsAuthenticated, IsCandidate)

    @extend_schema(
        operation_id="resumes_list",
        parameters=[PAGE_PARAMETER],
        responses={200: RESUME_LIST_RESPONSE},
    )
    def get(self, request):
        queryset = Resume.objects.filter(candidate=request.user).order_by(
            "-uploaded_at", "-id"
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(ResumeSerializer(page, many=True).data)

    @extend_schema(
        operation_id="resumes_create",
        request=RESUME_UPLOAD_REQUEST,
        responses={201: ResumeSerializer},
    )
    def post(self, request):
        serializer = ResumeUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        resume = serializer.save(candidate=request.user)
        return Response(ResumeSerializer(resume).data, status=status.HTTP_201_CREATED)


class ApplicationListCreateView(APIView):
    """List visible applications or submit a candidate application."""

    permission_classes = (IsAuthenticated,)

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsCandidate()]
        return [IsAuthenticated()]

    @extend_schema(
        operation_id="applications_list",
        parameters=[PAGE_PARAMETER],
        responses={200: APPLICATION_LIST_RESPONSE},
    )
    def get(self, request):
        queryset = Application.objects.select_related(
            "job", "job__company", "candidate", "resume"
        )
        if IsCandidate().has_permission(request, self):
            queryset = queryset.filter(candidate=request.user)
        elif IsEmployer().has_permission(request, self):
            queryset = queryset.filter(job__company__owner=request.user)
        else:
            queryset = queryset.none()
        queryset = queryset.order_by("-applied_at", "-id")
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            ApplicationSerializer(page, many=True).data
        )

    @extend_schema(
        operation_id="applications_create",
        request=APPLY_REQUEST,
        responses={201: ApplicationSerializer},
    )
    def post(self, request):
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data

        try:
            job = Job.objects.select_related("company").get(pk=values["job"])
        except Job.DoesNotExist as exc:
            raise ValidationError({"job": "The selected job does not exist."}) from exc
        try:
            resume = Resume.objects.get(pk=values["resume"])
        except Resume.DoesNotExist as exc:
            raise ValidationError(
                {"resume": "The selected resume does not exist."}
            ) from exc

        if not job.is_open:
            raise CodedAPIException(
                "job_closed", "This job is closed and cannot accept applications."
            )
        if not IsResumeOwner().has_object_permission(request, self, resume):
            raise CodedAPIException(
                "invalid_resume", "The selected resume does not belong to you."
            )
        if Application.objects.filter(candidate=request.user, job=job).exists():
            raise CodedAPIException(
                "duplicate_application", "You have already applied for this job."
            )

        try:
            # Store the application and notification together to avoid partial success.
            with transaction.atomic():
                application = Application.objects.create(
                    candidate=request.user, job=job, resume=resume
                )
                Notification.objects.create(
                    recipient=job.company.owner,
                    application=application,
                    # Match the database column limit for notification messages.
                    message=f"{request.user.username} applied for {job.title}"[:255],
                )
        except IntegrityError as exc:
            if (
                Application.objects.filter(candidate=request.user, job=job).first()
                is not None
            ):
                raise CodedAPIException(
                    "duplicate_application", "You have already applied for this job."
                ) from exc
            raise

        application = Application.objects.select_related(
            "job", "job__company", "candidate", "resume"
        ).get(pk=application.pk)
        return Response(
            ApplicationSerializer(application).data, status=status.HTTP_201_CREATED
        )


class ApplicationDetailView(APIView):
    """Return an application to its candidate or the job's employer."""

    permission_classes = (IsAuthenticated, CanViewApplication)

    @extend_schema(
        operation_id="applications_detail",
        responses={200: ApplicationSerializer},
    )
    def get(self, request, pk):
        application = get_object_or_404(
            Application.objects.select_related(
                "job", "job__company", "candidate", "resume"
            ),
            pk=pk,
        )
        self.check_object_permissions(request, application)
        return Response(ApplicationSerializer(application).data)


class ApplicationStatusView(APIView):
    """Update an application status for the job's employer."""

    permission_classes = (IsAuthenticated, IsEmployer, IsApplicationJobOwner)

    @extend_schema(
        operation_id="application_status_update",
        request=STATUS_REQUEST,
        responses={200: ApplicationSerializer},
    )
    def patch(self, request, pk):
        application = get_object_or_404(
            Application.objects.select_related(
                "job", "job__company", "candidate", "resume"
            ),
            pk=pk,
        )
        self.check_object_permissions(request, application)

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
            raise CodedAPIException(
                "invalid_transition", "This status transition is not allowed."
            )

        application.status = target
        application.save(update_fields=("status", "updated_at"))
        return Response(ApplicationSerializer(application).data)


class NotificationListView(APIView):
    """List notifications for the authenticated employer."""

    permission_classes = (IsAuthenticated, IsEmployer)

    @extend_schema(
        operation_id="notifications_list",
        parameters=[PAGE_PARAMETER],
        responses={200: NOTIFICATION_LIST_RESPONSE},
    )
    def get(self, request):
        queryset = (
            Notification.objects.filter(recipient=request.user)
            .select_related("application")
            .order_by("-created_at", "-id")
        )
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            NotificationSerializer(page, many=True).data
        )
