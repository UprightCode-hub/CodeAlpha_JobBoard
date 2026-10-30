"""Task 2 tests. Copy to jobs/tests_write.py in the repo. Agents must not edit it.
These tests check the database directly, so they do not depend on the Task 3 read endpoints."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.test import APITestCase

from jobs.models import Company, Job

User = get_user_model()
COMPANY = "/api/company/"
JOBS = "/api/jobs/"


def make_user(username, role):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="StrongPass123!",
        role=role,
    )


def job_payload(**overrides):
    data = {
        "title": "Backend Engineer",
        "description": "Build and maintain APIs",
        "location": "Lagos",
        "job_type": "full_time",
        "work_model": "remote",
        "experience_level": "mid",
        "min_years_experience": 3,
        "salary_min": 100000,
        "salary_max": 200000,
    }
    data.update(overrides)
    return data


class Base(APITestCase):
    def setUp(self):
        self.emp1 = make_user("emp1", "employer")
        self.emp2 = make_user("emp2", "employer")
        self.cand = make_user("cand", "candidate")

    def login(self, user):
        self.client.force_authenticate(user=user)

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(body["error"]["code"], code)
        self.assertTrue(body["error"]["message"].strip())


class CompanyTests(Base):
    def test_employer_creates_company(self):
        self.login(self.emp1)
        r = self.client.post(COMPANY, {"name": "Acme", "description": "Makes things"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["name"], "Acme")
        self.assertEqual(Company.objects.get().owner, self.emp1)

    def test_owner_cannot_be_set_from_body(self):
        self.login(self.emp1)
        r = self.client.post(
            COMPANY,
            {"name": "Acme", "description": "x", "owner": self.emp2.id},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Company.objects.get().owner, self.emp1)

    def test_candidate_cannot_create_company(self):
        self.login(self.cand)
        r = self.client.post(COMPANY, {"name": "Acme", "description": "x"}, format="json")
        self.assert_error(r, 403, "permission_denied")
        self.assertEqual(Company.objects.count(), 0)

    def test_candidate_cannot_read_company_endpoint(self):
        self.login(self.cand)
        self.assert_error(self.client.get(COMPANY), 403, "permission_denied")

    def test_anonymous_cannot_create_company(self):
        r = self.client.post(COMPANY, {"name": "Acme", "description": "x"}, format="json")
        self.assert_error(r, 401, "not_authenticated")

    def test_second_company_for_same_employer_rejected(self):
        self.login(self.emp1)
        self.client.post(COMPANY, {"name": "Acme", "description": "x"}, format="json")
        r = self.client.post(COMPANY, {"name": "Acme 2", "description": "y"}, format="json")
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Company.objects.count(), 1)

    def test_missing_name_rejected(self):
        self.login(self.emp1)
        r = self.client.post(COMPANY, {"description": "x"}, format="json")
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Company.objects.count(), 0)

    def test_get_own_company(self):
        Company.objects.create(owner=self.emp1, name="Acme", description="d")
        Company.objects.create(owner=self.emp2, name="Globex", description="d")
        self.login(self.emp1)
        r = self.client.get(COMPANY)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Acme")

    def test_get_company_when_none_exists_is_404(self):
        self.login(self.emp1)
        self.assert_error(self.client.get(COMPANY), 404, "not_found")

    def test_patch_changes_only_own_company(self):
        Company.objects.create(owner=self.emp1, name="Acme", description="d")
        Company.objects.create(owner=self.emp2, name="Globex", description="d")
        self.login(self.emp2)
        r = self.client.patch(COMPANY, {"name": "Globex Ltd"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Company.objects.get(owner=self.emp2).name, "Globex Ltd")
        self.assertEqual(Company.objects.get(owner=self.emp1).name, "Acme")

    def test_one_company_per_employer_enforced_by_database(self):
        Company.objects.create(owner=self.emp1, name="A", description="d")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Company.objects.create(owner=self.emp1, name="B", description="d")


class JobsBase(Base):
    def setUp(self):
        super().setUp()
        self.company1 = Company.objects.create(owner=self.emp1, name="Acme", description="d")
        self.company2 = Company.objects.create(owner=self.emp2, name="Globex", description="d")

    def make_job(self, company=None, **overrides):
        data = job_payload(**overrides)
        return Job.objects.create(company=company or self.company1, **data)


class JobModelTests(JobsBase):
    def test_new_job_is_open_by_default_and_has_timestamp(self):
        job = self.make_job()
        self.assertTrue(job.is_open)
        self.assertIsNotNone(job.created_at)

    def test_salary_is_optional_in_model(self):
        job = self.make_job(salary_min=None, salary_max=None)
        self.assertIsNone(job.salary_min)


class JobCreateTests(JobsBase):
    def test_employer_creates_job_for_own_company(self):
        self.login(self.emp1)
        r = self.client.post(JOBS, job_payload(), format="json")
        self.assertEqual(r.status_code, 201)
        job = Job.objects.get()
        self.assertEqual(job.company, self.company1)
        self.assertTrue(job.is_open)
        self.assertEqual(job.title, "Backend Engineer")

    def test_salary_can_be_left_out(self):
        self.login(self.emp1)
        payload = job_payload()
        del payload["salary_min"]
        del payload["salary_max"]
        r = self.client.post(JOBS, payload, format="json")
        self.assertEqual(r.status_code, 201)

    def test_company_cannot_be_set_from_body(self):
        self.login(self.emp1)
        r = self.client.post(JOBS, job_payload(company=self.company2.id), format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Job.objects.get().company, self.company1)

    def test_is_open_false_in_body_is_ignored(self):
        self.login(self.emp1)
        self.client.post(JOBS, job_payload(is_open=False), format="json")
        self.assertTrue(Job.objects.get().is_open)

    def test_candidate_cannot_create_job(self):
        self.login(self.cand)
        r = self.client.post(JOBS, job_payload(), format="json")
        self.assert_error(r, 403, "permission_denied")
        self.assertEqual(Job.objects.count(), 0)

    def test_anonymous_cannot_create_job(self):
        r = self.client.post(JOBS, job_payload(), format="json")
        self.assert_error(r, 401, "not_authenticated")

    def test_employer_without_company_rejected(self):
        emp3 = make_user("emp3", "employer")
        self.login(emp3)
        r = self.client.post(JOBS, job_payload(), format="json")
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Job.objects.count(), 0)

    def test_invalid_choices_rejected(self):
        self.login(self.emp1)
        for field, value in [
            ("job_type", "banana"),
            ("work_model", "banana"),
            ("experience_level", "banana"),
        ]:
            r = self.client.post(JOBS, job_payload(**{field: value}), format="json")
            self.assert_error(r, 400, "validation_error")
        self.assertEqual(Job.objects.count(), 0)

    def test_salary_min_above_max_rejected(self):
        self.login(self.emp1)
        r = self.client.post(JOBS, job_payload(salary_min=300000, salary_max=100000), format="json")
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Job.objects.count(), 0)

    def test_negative_salary_rejected(self):
        self.login(self.emp1)
        r = self.client.post(JOBS, job_payload(salary_min=-5), format="json")
        self.assert_error(r, 400, "validation_error")

    def test_negative_years_rejected(self):
        self.login(self.emp1)
        r = self.client.post(JOBS, job_payload(min_years_experience=-1), format="json")
        self.assert_error(r, 400, "validation_error")

    def test_missing_title_rejected(self):
        self.login(self.emp1)
        payload = job_payload()
        del payload["title"]
        r = self.client.post(JOBS, payload, format="json")
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Job.objects.count(), 0)


class JobUpdateTests(JobsBase):
    def setUp(self):
        super().setUp()
        self.job = self.make_job()
        self.url = f"{JOBS}{self.job.id}/"

    def test_owner_updates_job(self):
        self.login(self.emp1)
        r = self.client.patch(self.url, {"title": "Senior Engineer"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "Senior Engineer")

    def test_other_employer_cannot_update(self):
        self.login(self.emp2)
        r = self.client.patch(self.url, {"title": "Hacked"}, format="json")
        self.assert_error(r, 403, "permission_denied")
        self.job.refresh_from_db()
        self.assertEqual(self.job.title, "Backend Engineer")

    def test_candidate_cannot_update(self):
        self.login(self.cand)
        r = self.client.patch(self.url, {"title": "Hacked"}, format="json")
        self.assert_error(r, 403, "permission_denied")

    def test_anonymous_cannot_update(self):
        r = self.client.patch(self.url, {"title": "Hacked"}, format="json")
        self.assert_error(r, 401, "not_authenticated")

    def test_update_unknown_job_is_404(self):
        self.login(self.emp1)
        r = self.client.patch(f"{JOBS}999999/", {"title": "x"}, format="json")
        self.assert_error(r, 404, "not_found")

    def test_partial_salary_update_is_checked_against_saved_value(self):
        self.login(self.emp1)
        r = self.client.patch(self.url, {"salary_min": 300000}, format="json")
        self.assert_error(r, 400, "validation_error")
        self.job.refresh_from_db()
        self.assertEqual(self.job.salary_min, 100000)

    def test_patch_cannot_change_company(self):
        self.login(self.emp1)
        self.client.patch(self.url, {"company": self.company2.id}, format="json")
        self.job.refresh_from_db()
        self.assertEqual(self.job.company, self.company1)

    def test_patch_cannot_close_job(self):
        self.login(self.emp1)
        r = self.client.patch(self.url, {"is_open": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.job.refresh_from_db()
        self.assertTrue(self.job.is_open)


class JobCloseTests(JobsBase):
    def setUp(self):
        super().setUp()
        self.job = self.make_job()
        self.url = f"{JOBS}{self.job.id}/close/"

    def test_owner_closes_job(self):
        self.login(self.emp1)
        r = self.client.post(self.url)
        self.assertEqual(r.status_code, 200)
        self.job.refresh_from_db()
        self.assertFalse(self.job.is_open)

    def test_closing_twice_is_safe(self):
        self.login(self.emp1)
        self.client.post(self.url)
        r = self.client.post(self.url)
        self.assertEqual(r.status_code, 200)
        self.job.refresh_from_db()
        self.assertFalse(self.job.is_open)

    def test_other_employer_cannot_close(self):
        self.login(self.emp2)
        r = self.client.post(self.url)
        self.assert_error(r, 403, "permission_denied")
        self.job.refresh_from_db()
        self.assertTrue(self.job.is_open)

    def test_candidate_cannot_close(self):
        self.login(self.cand)
        self.assert_error(self.client.post(self.url), 403, "permission_denied")

    def test_anonymous_cannot_close(self):
        self.assert_error(self.client.post(self.url), 401, "not_authenticated")

    def test_close_unknown_job_is_404(self):
        self.login(self.emp1)
        r = self.client.post(f"{JOBS}999999/close/")
        self.assert_error(r, 404, "not_found")

    def test_close_url_rejects_get(self):
        self.login(self.emp1)
        self.assert_error(self.client.get(self.url), 405, "method_not_allowed")

    def test_job_is_never_deleted(self):
        self.login(self.emp1)
        r = self.client.delete(f"{JOBS}{self.job.id}/")
        self.assert_error(r, 405, "method_not_allowed")
        self.assertEqual(Job.objects.count(), 1)