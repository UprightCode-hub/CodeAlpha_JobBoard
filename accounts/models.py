from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLE_EMPLOYER = "employer"
    ROLE_CANDIDATE = "candidate"
    ROLE_CHOICES = [
        (ROLE_EMPLOYER, "Employer"),
        (ROLE_CANDIDATE, "Candidate"),
    ]

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=9, choices=ROLE_CHOICES)
