from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiTypes,
    extend_schema,
    inline_serializer,
)

from .models import Company, Job
from .permissions import IsEmployer, IsJobOwner
from .filters import filter_jobs
from .serializers import CompanySerializer, JobReadSerializer, JobSerializer


JOB_REQUEST_FIELDS = {
    "title": serializers.CharField(),
    "description": serializers.CharField(),
    "location": serializers.CharField(),
    "job_type": serializers.ChoiceField(
        choices=("full_time", "part_time", "contract", "internship")
    ),
    "work_model": serializers.ChoiceField(choices=("remote", "hybrid", "onsite")),
    "experience_level": serializers.ChoiceField(choices=("entry", "mid", "senior")),
    "min_years_experience": serializers.IntegerField(min_value=0, max_value=2147483647),
    "salary_min": serializers.IntegerField(min_value=0, max_value=2147483647, allow_null=True, required=False),
    "salary_max": serializers.IntegerField(min_value=0, max_value=2147483647, allow_null=True, required=False),
}
JOB_CREATE_REQUEST = inline_serializer(
    name="JobCreateRequest",
    fields=JOB_REQUEST_FIELDS,
)
JOB_PATCH_REQUEST = inline_serializer(
    name="JobPatchRequest",
    fields={
        "title": serializers.CharField(required=False),
        "description": serializers.CharField(required=False),
        "location": serializers.CharField(required=False),
        "job_type": serializers.ChoiceField(
            choices=("full_time", "part_time", "contract", "internship"),
            required=False,
        ),
        "work_model": serializers.ChoiceField(
            choices=("remote", "hybrid", "onsite"),
            required=False,
        ),
        "experience_level": serializers.ChoiceField(
            choices=("entry", "mid", "senior"),
            required=False,
        ),
        "min_years_experience": serializers.IntegerField(
            min_value=0,
            max_value=2147483647,
            required=False,
        ),
        "salary_min": serializers.IntegerField(
            min_value=0,
            max_value=2147483647,
            allow_null=True,
            required=False,
        ),
        "salary_max": serializers.IntegerField(
            min_value=0,
            max_value=2147483647,
            allow_null=True,
            required=False,
        ),
    },
)
JOB_LIST_RESPONSE = inline_serializer(
    name="JobListResponse",
    fields={
        "count": serializers.IntegerField(),
        "next": serializers.URLField(allow_null=True),
        "previous": serializers.URLField(allow_null=True),
        "results": JobReadSerializer(many=True),
    },
)
COMPANY_REQUEST = inline_serializer(
    name="CompanyRequest",
    fields={
        "name": serializers.CharField(),
        "description": serializers.CharField(),
    },
)
COMPANY_PATCH_REQUEST = inline_serializer(
    name="CompanyPatchRequest",
    fields={
        "name": serializers.CharField(required=False),
        "description": serializers.CharField(required=False),
    },
)
COMPANY_RESPONSE = inline_serializer(
    name="CompanyResponse",
    fields={
        "id": serializers.IntegerField(),
        "name": serializers.CharField(),
        "description": serializers.CharField(),
    },
)
JOB_FILTER_PARAMETERS = [
    OpenApiParameter("q", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter("location", OpenApiTypes.STR, OpenApiParameter.QUERY),
    OpenApiParameter(
        "job_type",
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        enum=("full_time", "part_time", "contract", "internship"),
    ),
    OpenApiParameter(
        "work_model",
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        enum=("remote", "hybrid", "onsite"),
    ),
    OpenApiParameter(
        "experience_level",
        OpenApiTypes.STR,
        OpenApiParameter.QUERY,
        enum=("entry", "mid", "senior"),
    ),
    OpenApiParameter("min_salary", OpenApiTypes.INT, OpenApiParameter.QUERY),
    OpenApiParameter(
        "posted_within_days", OpenApiTypes.INT, OpenApiParameter.QUERY
    ),
    OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY),
]


class CompanyView(APIView):
    """Create, retrieve, or update the authenticated employer's company."""

    permission_classes = (IsAuthenticated, IsEmployer)

    @extend_schema(
        operation_id="company_create",
        request=COMPANY_REQUEST,
        responses={201: COMPANY_RESPONSE},
    )
    def post(self, request):
        if Company.objects.filter(owner=request.user).exists():
            raise ValidationError("This employer already has a company.")
        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="company_retrieve",
        responses={200: COMPANY_RESPONSE},
    )
    def get(self, request):
        company = self.get_company(request.user)
        return Response(CompanySerializer(company).data)

    @extend_schema(
        operation_id="company_update",
        request=COMPANY_PATCH_REQUEST,
        responses={200: COMPANY_RESPONSE},
    )
    def patch(self, request):
        company = self.get_company(request.user)
        serializer = CompanySerializer(company, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @staticmethod
    def get_company(owner):
        try:
            return Company.objects.get(owner=owner)
        except Company.DoesNotExist as exc:
            raise NotFound("The requested resource was not found.") from exc


class JobCreateView(APIView):
    """List open jobs or create a job for the authenticated employer."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsEmployer()]

    @extend_schema(
        operation_id="jobs_list",
        parameters=JOB_FILTER_PARAMETERS,
        responses={200: JOB_LIST_RESPONSE},
    )
    def get(self, request):
        queryset = Job.objects.filter(is_open=True).select_related("company")
        queryset = filter_jobs(queryset, request.query_params).order_by("-created_at")
        page = self.paginate_queryset(queryset)
        serializer = JobReadSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)

    def paginate_queryset(self, queryset):
        self.paginator = PageNumberPagination()
        return self.paginator.paginate_queryset(queryset, self.request, view=self)

    def get_paginated_response(self, data):
        return self.paginator.get_paginated_response(data)

    @extend_schema(
        operation_id="jobs_create",
        request=JOB_CREATE_REQUEST,
        responses={201: JobReadSerializer},
    )
    def post(self, request):
        company = Company.objects.filter(owner=request.user).first()
        if company is None:
            raise ValidationError(
                "An employer must have a company before creating a job."
            )

        serializer = JobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = serializer.save(company=company)
        return Response(JobReadSerializer(job).data, status=status.HTTP_201_CREATED)


class OwnedJobView(APIView):
    """Provide shared access checks for job detail actions."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsEmployer(), IsJobOwner()]

    def get_owned_job(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        self.check_object_permissions(request, job)
        return job


class JobUpdateView(OwnedJobView):
    """Retrieve or update a job listing."""

    @extend_schema(
        operation_id="jobs_detail",
        responses={200: JobReadSerializer},
    )
    def get(self, request, pk):
        job = get_object_or_404(Job.objects.select_related("company"), pk=pk)
        if not job.is_open and not (
            request.user.is_authenticated
            and getattr(request.user, "role", None) == "employer"
            and job.company.owner_id == request.user.pk
        ):
            raise NotFound("The requested resource was not found.")
        return Response(JobReadSerializer(job).data)

    @extend_schema(
        operation_id="jobs_update",
        request=JOB_PATCH_REQUEST,
        responses={200: JobReadSerializer},
    )
    def patch(self, request, pk):
        job = self.get_owned_job(request, pk)
        serializer = JobSerializer(job, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        job = serializer.save()
        return Response(JobReadSerializer(job).data)


class JobCloseView(OwnedJobView):
    """Close a job listing."""

    @extend_schema(
        operation_id="jobs_close",
        request=None,
        responses={200: JobReadSerializer},
    )
    def post(self, request, pk):
        job = self.get_owned_job(request, pk)
        if job.is_open:
            job.is_open = False
            job.save(update_fields=("is_open",))
        return Response(JobReadSerializer(job).data)


class MyJobsView(APIView):
    """List jobs owned by the authenticated employer."""

    permission_classes = (IsAuthenticated, IsEmployer)

    @extend_schema(
        operation_id="my_jobs_list",
        parameters=[
            OpenApiParameter("page", OpenApiTypes.INT, OpenApiParameter.QUERY)
        ],
        responses={200: JOB_LIST_RESPONSE},
    )
    def get(self, request):
        queryset = Job.objects.filter(company__owner=request.user).select_related(
            "company"
        ).order_by("-created_at")
        paginator = self.paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            JobReadSerializer(page, many=True).data
        )
