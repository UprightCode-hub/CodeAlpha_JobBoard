from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Company, Job
from .permissions import IsEmployer, IsJobOwner
from .serializers import CompanySerializer, JobSerializer


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
    permission_classes = (IsAuthenticated, IsEmployer)

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
    permission_classes = (IsAuthenticated, IsEmployer, IsJobOwner)

    def get_owned_job(self, request, pk):
        job = get_object_or_404(Job, pk=pk)
        self.check_object_permissions(request, job)
        return job


class JobUpdateView(OwnedJobView):
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
