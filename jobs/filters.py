from datetime import timedelta

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Job


def filter_jobs(queryset, params):
    q = params.get("q")
    if q is not None and "\x00" in q:
        raise ValidationError({"q": "Null characters are not allowed."})
    if q:
        queryset = queryset.filter(title__icontains=q) | queryset.filter(
            description__icontains=q
        )

    location = params.get("location")
    if location is not None and "\x00" in location:
        raise ValidationError({"location": "Null characters are not allowed."})
    if location:
        queryset = queryset.filter(location__icontains=location)

    choices = {
        "job_type": {value for value, _ in Job.JOB_TYPE_CHOICES},
        "work_model": {value for value, _ in Job.WORK_MODEL_CHOICES},
        "experience_level": {value for value, _ in Job.EXPERIENCE_LEVEL_CHOICES},
    }
    for name, allowed in choices.items():
        value = params.get(name)
        if value:
            if value not in allowed:
                raise ValidationError({name: "Select a valid choice."})
            queryset = queryset.filter(**{name: value})

    min_salary = params.get("min_salary")
    if min_salary is not None:
        parsed = _positive_integer(
            min_salary, "min_salary", allow_zero=True, max_value=2147483647
        )
        queryset = queryset.filter(salary_max__gte=parsed, salary_max__isnull=False)

    posted_within_days = params.get("posted_within_days")
    if posted_within_days is not None:
        days = _positive_integer(posted_within_days, "posted_within_days")
        queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=days))

    return queryset


def _positive_integer(value, field, allow_zero=False, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValidationError({field: "A valid integer is required."})
    if parsed < (0 if allow_zero else 1):
        raise ValidationError({field: "A valid integer is required."})
    if max_value is not None and parsed > max_value:
        raise ValidationError({field: "A valid integer is required."})
    return parsed
