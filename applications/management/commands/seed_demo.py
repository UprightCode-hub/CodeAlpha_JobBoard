from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from jobs.models import Company, Job


DEMO_PASSWORD = "JobBoardDemo123!"

DEMO_JOBS = (
    {
        "title": "Remote Backend Engineer",
        "description": "Build and maintain reliable web APIs.",
        "location": "Lagos",
        "job_type": "full_time",
        "work_model": "remote",
        "experience_level": "mid",
        "min_years_experience": 3,
        "salary_min": 100000,
        "salary_max": 200000,
    },
    {
        "title": "Hybrid Product Designer",
        "description": "Design accessible product experiences.",
        "location": "Abuja",
        "job_type": "part_time",
        "work_model": "hybrid",
        "experience_level": "entry",
        "min_years_experience": 0,
        "salary_min": 50000,
        "salary_max": 90000,
    },
    {
        "title": "Onsite Data Analyst",
        "description": "Turn business data into useful insights.",
        "location": "Port Harcourt",
        "job_type": "contract",
        "work_model": "onsite",
        "experience_level": "senior",
        "min_years_experience": 5,
        "salary_min": 150000,
        "salary_max": 250000,
    },
)


class Command(BaseCommand):
    help = "Create repeatable demo accounts, a company, and open jobs."

    @transaction.atomic
    def handle(self, *args, **options):
        employer, employer_created = User.objects.get_or_create(
            username="demo_employer",
            defaults={
                "email": "demo_employer@example.com",
                "role": User.ROLE_EMPLOYER,
            },
        )
        if employer_created:
            employer.set_password(DEMO_PASSWORD)
            employer.save(update_fields=("password",))

        candidate, candidate_created = User.objects.get_or_create(
            username="demo_candidate",
            defaults={
                "email": "demo_candidate@example.com",
                "role": User.ROLE_CANDIDATE,
            },
        )
        if candidate_created:
            candidate.set_password(DEMO_PASSWORD)
            candidate.save(update_fields=("password",))

        company, _ = Company.objects.get_or_create(
            owner=employer,
            defaults={
                "name": "Demo Company",
                "description": "A sample employer for trying the job board.",
            },
        )

        for job_data in DEMO_JOBS:
            title = job_data["title"]
            defaults = {key: value for key, value in job_data.items() if key != "title"}
            Job.objects.get_or_create(
                company=company,
                title=title,
                defaults=defaults,
            )

        self.stdout.write(f"Employer username: {employer.username}")
        self.stdout.write(f"Candidate username: {candidate.username}")
        self.stdout.write(f"Demo password: {DEMO_PASSWORD}")
