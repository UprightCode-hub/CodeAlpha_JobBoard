from django.conf import settings
from django.db import models


class Company(models.Model):
    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company",
    )
    name = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return self.name


class Job(models.Model):
    JOB_TYPE_CHOICES = [
        ("full_time", "Full time"),
        ("part_time", "Part time"),
        ("contract", "Contract"),
        ("internship", "Internship"),
    ]
    WORK_MODEL_CHOICES = [
        ("remote", "Remote"),
        ("hybrid", "Hybrid"),
        ("onsite", "Onsite"),
    ]
    EXPERIENCE_LEVEL_CHOICES = [
        ("entry", "Entry"),
        ("mid", "Mid"),
        ("senior", "Senior"),
    ]

    company = models.ForeignKey(
        Company,
        on_delete=models.PROTECT,
        related_name="jobs",
    )
    title = models.CharField(max_length=255)
    description = models.TextField()
    location = models.CharField(max_length=255)
    job_type = models.CharField(max_length=10, choices=JOB_TYPE_CHOICES)
    work_model = models.CharField(max_length=6, choices=WORK_MODEL_CHOICES)
    experience_level = models.CharField(max_length=6, choices=EXPERIENCE_LEVEL_CHOICES)
    min_years_experience = models.IntegerField()
    salary_min = models.IntegerField(null=True, blank=True)
    salary_max = models.IntegerField(null=True, blank=True)
    is_open = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title
