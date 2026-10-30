"""Tests for JSON 404 responses and job write response fields with DEBUG enabled."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from jobs.models import Company

User = get_user_model()

JOB_RESPONSE_FIELDS = {
    "id", "title", "description", "location", "job_type", "work_model",
    "experience_level", "min_years_experience", "salary_min", "salary_max",
    "is_open", "created_at", "company_name",
}


class UnknownUrlJsonTests(TestCase):
    """Unknown URLs return the JSON not_found error with DEBUG on and off."""

    def assert_json_not_found(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 404, path)
        self.assertIn("application/json", response["Content-Type"], path)
        body = response.json()
        self.assertEqual(body["error"]["code"], "not_found", path)
        self.assertTrue(body["error"]["message"], path)

    def test_unknown_urls_are_json_with_debug_off(self):
        with override_settings(DEBUG=False):
            for path in ("/api/nope/", "/nope/", "/api/jobs/abc/"):
                self.assert_json_not_found(path)

    def test_unknown_urls_are_json_with_debug_on(self):
        with override_settings(DEBUG=True):
            for path in ("/api/nope/", "/nope/", "/api/jobs/abc/"):
                self.assert_json_not_found(path)

    def test_docs_and_schema_still_work_with_debug_on(self):
        # The catch-all route must not swallow real routes.
        with override_settings(DEBUG=True):
            self.assertEqual(self.client.get("/api/schema/").status_code, 200)
            self.assertEqual(self.client.get("/api/docs/").status_code, 200)


class JobWriteResponseShapeTests(APITestCase):
    """POST, PATCH, and close return the same fields as job reads."""

    def setUp(self):
        self.employer = User.objects.create_user(
            username="shape_employer", email="shape_employer@example.com",
            password="StrongPass123!", role="employer",
        )
        Company.objects.create(owner=self.employer, name="Shape Co", description="x")
        token = self.client.post(
            "/api/auth/login/",
            {"username": "shape_employer", "password": "StrongPass123!"},
            format="json",
        ).json()["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)

    def create_job(self):
        return self.client.post(
            "/api/jobs/",
            {
                "title": "Shape Job", "description": "d", "location": "Lagos",
                "job_type": "full_time", "work_model": "remote",
                "experience_level": "entry", "min_years_experience": 0,
            },
            format="json",
        )

    def test_create_response_has_job_read_fields(self):
        response = self.create_job()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.json().keys()), JOB_RESPONSE_FIELDS)
        self.assertEqual(response.json()["company_name"], "Shape Co")

    def test_patch_response_has_job_read_fields(self):
        job_id = self.create_job().json()["id"]
        response = self.client.patch(f"/api/jobs/{job_id}/", {"title": "Renamed"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json().keys()), JOB_RESPONSE_FIELDS)
        self.assertEqual(response.json()["title"], "Renamed")

    def test_close_response_has_job_read_fields(self):
        job_id = self.create_job().json()["id"]
        response = self.client.post(f"/api/jobs/{job_id}/close/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json().keys()), JOB_RESPONSE_FIELDS)
        self.assertFalse(response.json()["is_open"])
