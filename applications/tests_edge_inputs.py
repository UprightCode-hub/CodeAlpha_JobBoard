"""Tests that edge inputs return validation errors instead of server errors."""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

from applications.models import Resume
from jobs.models import Company, Job

User = get_user_model()
PASSWORD = "StrongPass123!"
HUGE = 99999999999999999999  # far beyond a 32 bit integer


class EdgeInputBase(APITestCase):
    def setUp(self):
        self.employer = User.objects.create_user(
            username="edge_employer", email="edge_employer@example.com",
            password=PASSWORD, role="employer",
        )
        self.company = Company.objects.create(owner=self.employer, name="Edge Co", description="x")
        self.candidate = User.objects.create_user(
            username="edge_candidate", email="edge_candidate@example.com",
            password=PASSWORD, role="candidate",
        )

    def login(self, username):
        token = self.client.post(
            "/api/auth/login/", {"username": username, "password": PASSWORD}, format="json"
        ).json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)

    def job_payload(self, **overrides):
        data = {
            "title": "Edge Job", "description": "d", "location": "Lagos",
            "job_type": "full_time", "work_model": "remote",
            "experience_level": "entry", "min_years_experience": 0,
        }
        data.update(overrides)
        return data

    def make_job(self, title="Edge Job"):
        return Job.objects.create(
            company=self.company, title=title, description="d", location="Lagos",
            job_type="full_time", work_model="remote", experience_level="entry",
            min_years_experience=0,
        )

    def assert_validation_error(self, response):
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "validation_error")


class JobInputLimitTests(EdgeInputBase):
    def setUp(self):
        super().setUp()
        self.login("edge_employer")

    def test_title_over_255_characters_is_400(self):
        r = self.client.post("/api/jobs/", self.job_payload(title="T" * 256), format="json")
        self.assert_validation_error(r)

    def test_location_over_255_characters_is_400(self):
        r = self.client.post("/api/jobs/", self.job_payload(location="L" * 256), format="json")
        self.assert_validation_error(r)

    def test_huge_salary_max_is_400(self):
        r = self.client.post("/api/jobs/", self.job_payload(salary_min=1, salary_max=HUGE), format="json")
        self.assert_validation_error(r)

    def test_huge_salary_min_is_400(self):
        r = self.client.post("/api/jobs/", self.job_payload(salary_min=HUGE, salary_max=HUGE + 1), format="json")
        self.assert_validation_error(r)

    def test_huge_min_years_is_400(self):
        r = self.client.post("/api/jobs/", self.job_payload(min_years_experience=HUGE), format="json")
        self.assert_validation_error(r)

    def test_null_character_in_title_is_400(self):
        r = self.client.post("/api/jobs/", self.job_payload(title="bad\x00title"), format="json")
        self.assert_validation_error(r)

    def test_unicode_title_is_stored_and_searchable(self):
        r = self.client.post("/api/jobs/", self.job_payload(title="Développeur 🚀"), format="json")
        self.assertEqual(r.status_code, 201, r.content)
        found = self.client.get("/api/jobs/", {"q": "🚀"})
        self.assertEqual(found.status_code, 200, found.content)
        self.assertEqual(found.json()["count"], 1)


class FilterAndPageEdgeTests(EdgeInputBase):
    def test_huge_min_salary_filter_never_500(self):
        r = self.client.get("/api/jobs/", {"min_salary": HUGE})
        self.assertIn(r.status_code, (200, 400), r.content)

    def test_null_character_in_search_never_500(self):
        r = self.client.get("/api/jobs/", {"q": "a\x00b"})
        self.assertIn(r.status_code, (200, 400), r.content)

    def test_bad_page_values_are_404_not_found(self):
        for page in ("abc", "0", "-1"):
            r = self.client.get("/api/jobs/", {"page": page})
            self.assertEqual(r.status_code, 404, (page, r.content))
            self.assertEqual(r.json()["error"]["code"], "not_found", page)


class RegistrationEdgeTests(EdgeInputBase):
    def register(self, **overrides):
        data = {
            "username": "edge_new", "email": "edge_new@example.com",
            "password": PASSWORD, "role": "candidate",
        }
        data.update(overrides)
        return self.client.post("/api/auth/register/", data, format="json")

    def test_username_over_150_characters_is_400(self):
        self.assert_validation_error(self.register(username="u" * 151))

    def test_email_over_254_characters_is_400(self):
        self.assert_validation_error(self.register(email="e" * 250 + "@example.com"))

    def test_null_character_in_username_is_400(self):
        self.assert_validation_error(self.register(username="bad\x00name"))


class ApplyMessageLengthTests(EdgeInputBase):
    def test_apply_to_job_with_255_character_title_never_500(self):
        """The notification message is 'username applied for title' and is capped at 255."""
        job = self.make_job(title="T" * 255)
        resume = Resume.objects.create(candidate=self.candidate, title="cv", file="resumes/edge.pdf")
        self.login("edge_candidate")
        r = self.client.post("/api/applications/", {"job": job.id, "resume": resume.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        # Do not query the database after a possible database error; the checks below
        # use the notification list, which only runs if the apply worked.
        self.login("edge_employer")
        notes = self.client.get("/api/notifications/").json()["results"]
        self.assertEqual(len(notes), 1)
        self.assertLessEqual(len(notes[0]["message"]), 255)
        self.assertTrue(notes[0]["message"].startswith("edge_candidate applied for "))
