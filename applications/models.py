from django.conf import settings
from django.db import models


class Resume(models.Model):
    """Candidate-owned resume and uploaded file."""

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="resumes",
    )
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to="resumes/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Application(models.Model):
    """Candidate application linking a job and a resume."""

    STATUS_CHOICES = [
        ("applied", "Applied"),
        ("reviewing", "Reviewing"),
        ("shortlisted", "Shortlisted"),
        ("rejected", "Rejected"),
        ("hired", "Hired"),
    ]

    candidate = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="applications",
    )
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.PROTECT,
        related_name="applications",
    )
    resume = models.ForeignKey(
        Resume,
        on_delete=models.PROTECT,
        related_name="applications",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="applied",
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Keep duplicate applications out of the database, including concurrent requests.
            models.UniqueConstraint(
                fields=("candidate", "job"),
                name="unique_application_per_candidate_job",
            )
        ]

    def __str__(self):
        return f"{self.candidate} - {self.job}"


class Notification(models.Model):
    """Notification sent to an employer about an application."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.message
