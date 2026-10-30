from django.urls import path

from .views import CompanyView, JobCloseView, JobCreateView, JobUpdateView

urlpatterns = [
    path("company/", CompanyView.as_view(), name="company"),
    path("jobs/", JobCreateView.as_view(), name="job-create"),
    path("jobs/<int:pk>/", JobUpdateView.as_view(), name="job-update"),
    path("jobs/<int:pk>/close/", JobCloseView.as_view(), name="job-close"),
]
