"""Tests for public job reads, filters, and pagination."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from jobs.models import Company, Job

User = get_user_model()
JOBS = "/api/jobs/"
MY_JOBS = "/api/my/jobs/"

FIELDS = {
    "id", "title", "description", "location", "job_type", "work_model",
    "experience_level", "min_years_experience", "salary_min", "salary_max",
    "is_open", "created_at", "company_name",
}


def make_user(username, role):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="StrongPass123!",
        role=role,
    )


class ReadBase(APITestCase):
    def setUp(self):
        self.emp1 = make_user("emp1", "employer")
        self.emp2 = make_user("emp2", "employer")
        self.cand = make_user("cand", "candidate")
        self.c1 = Company.objects.create(owner=self.emp1, name="Acme", description="d")
        self.c2 = Company.objects.create(owner=self.emp2, name="Globex", description="d")
        now = timezone.now()
        self.j1 = self.make_job(
            self.c1, now - timedelta(days=10),
            title="Python Developer", description="Build Django APIs",
            location="Lagos, Nigeria", job_type="full_time", work_model="remote",
            experience_level="entry", min_years_experience=0,
            salary_min=100000, salary_max=150000,
        )
        self.j2 = self.make_job(
            self.c1, now - timedelta(days=5),
            title="Java Engineer", description="Spring boot services",
            location="Abuja", job_type="part_time", work_model="onsite",
            experience_level="mid", min_years_experience=3,
            salary_min=200000, salary_max=300000,
        )
        self.j3 = self.make_job(
            self.c2, now - timedelta(hours=1),
            title="Data Analyst", description="Analyse sales data",
            location="Lagos", job_type="contract", work_model="hybrid",
            experience_level="senior", min_years_experience=5,
        )
        self.j4 = self.make_job(
            self.c2, now - timedelta(days=4),
            title="Closed Role", description="Gone",
            location="Lagos", job_type="full_time", work_model="remote",
            experience_level="mid", min_years_experience=1, is_open=False,
        )
        self.j5 = self.make_job(
            self.c1, now - timedelta(days=3),
            title="Old Role", description="Gone too",
            location="Ibadan", job_type="full_time", work_model="onsite",
            experience_level="mid", min_years_experience=1, is_open=False,
        )

    def make_job(self, company, created_at, **fields):
        job = Job.objects.create(company=company, **fields)
        Job.objects.filter(pk=job.pk).update(created_at=created_at)
        job.refresh_from_db()
        return job

    def login(self, user):
        self.client.force_authenticate(user=user)

    def titles(self, response):
        return [item["title"] for item in response.json()["results"]]

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(body["error"]["code"], code)
        self.assertTrue(body["error"]["message"].strip())


class JobListTests(ReadBase):
    def test_anonymous_sees_only_open_jobs(self):
        r = self.client.get(JOBS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            set(self.titles(r)), {"Python Developer", "Java Engineer", "Data Analyst"}
        )
        self.assertEqual(r.json()["count"], 3)

    def test_closed_jobs_never_listed_for_anyone(self):
        for user in (self.cand, self.emp1, self.emp2):
            self.login(user)
            r = self.client.get(JOBS)
            self.assertNotIn("Closed Role", self.titles(r))
            self.assertNotIn("Old Role", self.titles(r))

    def test_newest_first(self):
        r = self.client.get(JOBS)
        self.assertEqual(
            self.titles(r), ["Data Analyst", "Java Engineer", "Python Developer"]
        )

    def test_response_has_pagination_keys(self):
        body = self.client.get(JOBS).json()
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, body)

    def test_item_has_exactly_the_agreed_fields(self):
        item = self.client.get(JOBS).json()["results"][0]
        self.assertEqual(set(item.keys()), FIELDS)

    def test_company_name_is_shown(self):
        item = self.client.get(JOBS).json()["results"][0]
        self.assertEqual(item["company_name"], "Globex")

    def test_no_owner_data_leaks(self):
        raw = self.client.get(JOBS).content.decode()
        self.assertNotIn("example.com", raw)
        self.assertNotIn("emp1", raw)
        self.assertNotIn("owner", raw)

    def test_pagination_ten_per_page(self):
        for i in range(9):
            Job.objects.create(
                company=self.c1, title=f"Extra {i}", description="d",
                location="Lagos", job_type="full_time", work_model="remote",
                experience_level="mid", min_years_experience=1,
            )
        page1 = self.client.get(JOBS).json()
        page2 = self.client.get(JOBS + "?page=2").json()
        self.assertEqual(page1["count"], 12)
        self.assertEqual(len(page1["results"]), 10)
        self.assertEqual(len(page2["results"]), 2)

    def test_page_out_of_range_is_graceful_404(self):
        r = self.client.get(JOBS + "?page=99")
        self.assert_error(r, 404, "not_found")

    def test_list_does_not_query_company_once_per_job(self):
        for i in range(9):
            Job.objects.create(
                company=self.c2 if i % 2 else self.c1, title=f"Extra {i}",
                description="d", location="Lagos", job_type="full_time",
                work_model="remote", experience_level="mid", min_years_experience=1,
            )
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(JOBS)
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(len(ctx), 4)


class JobFilterTests(ReadBase):
    def get_titles(self, query):
        r = self.client.get(JOBS + query)
        self.assertEqual(r.status_code, 200, r.content)
        return set(self.titles(r))

    def test_q_matches_title(self):
        self.assertEqual(self.get_titles("?q=python"), {"Python Developer"})

    def test_q_matches_description(self):
        self.assertEqual(self.get_titles("?q=spring"), {"Java Engineer"})

    def test_q_is_case_insensitive(self):
        self.assertEqual(self.get_titles("?q=PYTHON"), {"Python Developer"})

    def test_q_with_no_match_returns_empty_list(self):
        r = self.client.get(JOBS + "?q=zzzzzz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 0)
        self.assertEqual(r.json()["results"], [])

    def test_location_contains_and_ignores_case(self):
        self.assertEqual(
            self.get_titles("?location=lagos"), {"Python Developer", "Data Analyst"}
        )

    def test_job_type(self):
        self.assertEqual(self.get_titles("?job_type=contract"), {"Data Analyst"})

    def test_work_model(self):
        self.assertEqual(self.get_titles("?work_model=remote"), {"Python Developer"})

    def test_experience_level(self):
        self.assertEqual(self.get_titles("?experience_level=senior"), {"Data Analyst"})

    def test_min_salary_uses_salary_max_and_drops_jobs_without_salary(self):
        self.assertEqual(self.get_titles("?min_salary=250000"), {"Java Engineer"})
        self.assertEqual(
            self.get_titles("?min_salary=100000"), {"Python Developer", "Java Engineer"}
        )

    def test_posted_within_days(self):
        self.assertEqual(self.get_titles("?posted_within_days=1"), {"Data Analyst"})
        self.assertEqual(
            self.get_titles("?posted_within_days=7"), {"Data Analyst", "Java Engineer"}
        )
        self.assertEqual(
            self.get_titles("?posted_within_days=30"),
            {"Data Analyst", "Java Engineer", "Python Developer"},
        )

    def test_filters_combine(self):
        self.assertEqual(
            self.get_titles("?location=lagos&work_model=remote"), {"Python Developer"}
        )
        self.assertEqual(self.get_titles("?job_type=full_time&location=abuja"), set())

    def test_filters_never_show_closed_jobs(self):
        self.assertNotIn("Closed Role", self.get_titles("?location=lagos"))

    def test_invalid_filter_values_rejected(self):
        for query in [
            "?job_type=banana",
            "?work_model=banana",
            "?experience_level=banana",
            "?min_salary=abc",
            "?min_salary=-5",
            "?posted_within_days=abc",
            "?posted_within_days=0",
        ]:
            r = self.client.get(JOBS + query)
            self.assert_error(r, 400, "validation_error")

    def test_sql_looking_text_is_harmless(self):
        before = Job.objects.count()
        for query in ["?q='; DROP TABLE jobs_job;--", "?location=' OR '1'='1"]:
            r = self.client.get(JOBS + query)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["count"], 0)
        self.assertEqual(Job.objects.count(), before)


class JobDetailTests(ReadBase):
    def test_anyone_can_read_open_job(self):
        r = self.client.get(f"{JOBS}{self.j1.id}/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(set(body.keys()), FIELDS)
        self.assertEqual(body["title"], "Python Developer")
        self.assertEqual(body["company_name"], "Acme")

    def test_closed_job_is_404_for_anonymous(self):
        r = self.client.get(f"{JOBS}{self.j4.id}/")
        self.assert_error(r, 404, "not_found")

    def test_closed_job_is_404_for_candidate_and_other_employer(self):
        for user in (self.cand, self.emp1):
            self.login(user)
            r = self.client.get(f"{JOBS}{self.j4.id}/")
            self.assert_error(r, 404, "not_found")

    def test_owner_can_read_own_closed_job(self):
        self.login(self.emp2)
        r = self.client.get(f"{JOBS}{self.j4.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["is_open"])

    def test_unknown_job_is_404(self):
        self.assert_error(self.client.get(f"{JOBS}999999/"), 404, "not_found")

    def test_non_numeric_id_is_404(self):
        self.assert_error(self.client.get(f"{JOBS}abc/"), 404, "not_found")


class MyJobsTests(ReadBase):
    def test_employer_sees_own_open_and_closed_jobs_only(self):
        self.login(self.emp1)
        r = self.client.get(MY_JOBS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            set(self.titles(r)), {"Python Developer", "Java Engineer", "Old Role"}
        )

    def test_other_employer_sees_their_own(self):
        self.login(self.emp2)
        r = self.client.get(MY_JOBS)
        self.assertEqual(set(self.titles(r)), {"Data Analyst", "Closed Role"})

    def test_employer_with_no_jobs_gets_empty_list(self):
        emp3 = make_user("emp3", "employer")
        self.login(emp3)
        r = self.client.get(MY_JOBS)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 0)

    def test_candidate_cannot_use_my_jobs(self):
        self.login(self.cand)
        self.assert_error(self.client.get(MY_JOBS), 403, "permission_denied")

    def test_anonymous_cannot_use_my_jobs(self):
        self.assert_error(self.client.get(MY_JOBS), 401, "not_authenticated")

    def test_my_jobs_is_paginated(self):
        self.login(self.emp1)
        body = self.client.get(MY_JOBS).json()
        for key in ("count", "next", "previous", "results"):
            self.assertIn(key, body)
