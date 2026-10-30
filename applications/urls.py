from django.urls import path

from .views import (
    ApplicationDetailView,
    ApplicationListCreateView,
    ApplicationStatusView,
    NotificationListView,
    ResumeListCreateView,
)

urlpatterns = [
    path("resumes/", ResumeListCreateView.as_view(), name="resumes"),
    path("applications/", ApplicationListCreateView.as_view(), name="applications"),
    path("applications/<int:pk>/", ApplicationDetailView.as_view(), name="application-detail"),
    path(
        "applications/<int:pk>/status/",
        ApplicationStatusView.as_view(),
        name="application-status",
    ),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
]
