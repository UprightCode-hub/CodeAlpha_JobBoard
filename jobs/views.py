from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, Job
from .permissions import IsEmployer, IsJobOwner
from .filters import filter_jobs
from .serializers import CompanySerializer, JobReadSerializer, JobSerializer


class CompanyView(APIView):
    permission_classes = (IsAuthenticated, IsEmployer)

    def post(self, request):
        if Company.objects.filter(owner=request.user).exists():
            raise ValidationError("This employer already has a company.")
        serializer = CompanySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get(self, request):
        company = self.get_company(request.user)
        return Response(CompanySerializer(company).data)

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
    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsEmployer()]

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

    def post(self, request):
        company = Company.objects.filter(owner=request.user).first()
        if company is None:
            raise ValidationError(
                "An employer must have a company before creating a job."
            )

        serializer = JobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(company=company)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OwnedJobView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsAuthenticated(), IsEmployer(), IsJobOwner()]

    def get_owned_job(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        self.check_object_permissions(request, job)
        return job


class JobUpdateView(OwnedJobView):
    def get(self, request, pk):
        job = get_object_or_404(Job.objects.select_related("company"), pk=pk)
        if not job.is_open and not (
            request.user.is_authenticated
            and getattr(request.user, "role", None) == "employer"
            and job.company.owner_id == request.user.pk
        ):
            raise NotFound("The requested resource was not found.")
        return Response(JobReadSerializer(job).data)

    def patch(self, request, pk):
        job = self.get_owned_job(request, pk)
        serializer = JobSerializer(job, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class JobCloseView(OwnedJobView):
    def post(self, request, pk):
        job = self.get_owned_job(request, pk)
        if job.is_open:
            job.is_open = False
            job.save(update_fields=("is_open",))
        return Response(JobSerializer(job).data)


class MyJobsView(APIView):
    permission_classes = (IsAuthenticated, IsEmployer)

    def get(self, request):
        queryset = Job.objects.filter(company__owner=request.user).select_related(
            "company"
        ).order_by("-created_at")
        paginator = self.paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(
            JobReadSerializer(page, many=True).data
        )
