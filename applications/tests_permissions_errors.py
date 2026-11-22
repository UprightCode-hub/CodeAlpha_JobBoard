"""Consolidated permissions and the unified JSON error envelope.

Drop into applications/. Run:
python manage.py test applications.tests_permissions_errors

Every error response must be exactly {"error": {"code": str, "message": str}}.
"""

import re
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from applications.models import Application, Resume
from jobs.models import Company, Job

User = get_user_model()

PASSWORD = "Str0ng-Passw0rd!x9"


def make_user(username, role):
    return User.objects.create(
        username=username, email=f"{username}@example.com", role=role
    )


JOB_BODY = {
    "title": "QA Engineer",
    "description": "Break things",
    "location": "Ibadan",
    "job_type": "full_time",
    "work_model": "remote",
    "experience_level": "mid",
    "min_years_experience": 1,
}


class EnvelopeMixin:
    assertEqual: Any
    assertTrue: Any
    assertIsInstance: Any
    assertNotIn: Any

    def assert_envelope(self, response, status, code=None):
        self.assertEqual(response.status_code, status, response.content[:400])
        self.assertTrue(response["Content-Type"].startswith("application/json"))
        body = response.json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(set(body["error"]), {"code", "message"})
        self.assertIsInstance(body["error"]["code"], str)
        self.assertIsInstance(body["error"]["message"], str)
        self.assertTrue(body["error"]["message"].strip())
        if code is not None:
            self.assertEqual(body["error"]["code"], code)
        text = response.content.decode()
        for leak in ("Traceback", "site-packages", "django.db.utils"):
            self.assertNotIn(leak, text)


class World(EnvelopeMixin, APITestCase):
    def setUp(self):
        self.cand = make_user("cand", "candidate")
        self.cand2 = make_user("cand2", "candidate")
        self.emp1 = make_user("emp1", "employer")
        self.emp2 = make_user("emp2", "employer")
        self.company1 = Company.objects.create(
            owner=self.emp1, name="Acme", description="d"
        )
        self.company2 = Company.objects.create(
            owner=self.emp2, name="Globex", description="d"
        )
        self.job = self.new_job()
        self.closed_job = self.new_job(is_open=False)
        self.resume = Resume.objects.create(
            candidate=self.cand, title="CV", file="resumes/cv.pdf"
        )
        self.resume2 = Resume.objects.create(
            candidate=self.cand2, title="CV2", file="resumes/cv2.pdf"
        )
        self.app = Application.objects.create(
            candidate=self.cand, job=self.job, resume=self.resume, status="applied"
        )
        self.actors = {
            "anon": None,
            "cand": self.cand,
            "cand2": self.cand2,
            "emp1": self.emp1,
            "emp2": self.emp2,
        }

    def new_job(self, company=None, is_open=True):
        return Job.objects.create(
            company=company or self.company1,
            title="Backend Engineer",
            description="Build APIs",
            location="Lagos",
            job_type="full_time",
            work_model="remote",
            experience_level="mid",
            min_years_experience=2,
            is_open=is_open,
        )

    def call(self, actor, method, url, data=None, fmt="json"):
        self.client.credentials()
        self.client.force_authenticate(user=self.actors[actor])
        kwargs = {} if method == "get" else {"data": data, "format": fmt}
        return getattr(self.client, method)(url, **kwargs)


# --------------------------------------------------------------- the matrix


class PermissionMatrixTests(World):
    def rows(self):
        """(label, method, url_fn, data_fn, format, {actor: (status, code)})"""
        n = "not_authenticated"
        p = "permission_denied"
        nf = "not_found"
        v = "validation_error"
        return [
            (
                "me",
                "get",
                lambda: reverse("me"),
                None,
                "json",
                {"anon": (401, n), "cand": (200, None), "emp1": (200, None)},
            ),
            (
                "company get",
                "get",
                lambda: reverse("company"),
                None,
                "json",
                {
                    "anon": (401, n),
                    "cand": (403, p),
                    "cand2": (403, p),
                    "emp1": (200, None),
                    "emp2": (200, None),
                },
            ),
            (
                "company patch",
                "patch",
                lambda: reverse("company"),
                lambda: {"description": "new"},
                "json",
                {"anon": (401, n), "cand": (403, p), "emp1": (200, None)},
            ),
            (
                "company create (already has one)",
                "post",
                lambda: reverse("company"),
                lambda: {"name": "Second", "description": "d"},
                "json",
                {"anon": (401, n), "cand": (403, p), "emp1": (400, v)},
            ),
            (
                "job create",
                "post",
                lambda: reverse("job-create"),
                lambda: dict(JOB_BODY),
                "json",
                {"anon": (401, n), "cand": (403, p), "emp1": (201, None)},
            ),
            (
                "job patch",
                "patch",
                lambda: reverse("job-update", args=[self.job.pk]),
                lambda: {"title": "Renamed"},
                "json",
                {
                    "anon": (401, n),
                    "cand": (403, p),
                    "emp2": (403, p),
                    "emp1": (200, None),
                },
            ),
            (
                "job close",
                "post",
                lambda: reverse("job-close", args=[self.new_job().pk]),
                None,
                "json",
                {
                    "anon": (401, n),
                    "cand": (403, p),
                    "emp2": (403, p),
                    "emp1": (200, None),
                },
            ),
            (
                "job patch unknown id",
                "patch",
                lambda: reverse("job-update", args=[999999]),
                lambda: {"title": "x"},
                "json",
                {"emp1": (404, nf)},
            ),
            (
                "job get unknown id",
                "get",
                lambda: reverse("job-update", args=[999999]),
                None,
                "json",
                {"anon": (404, nf), "emp1": (404, nf)},
            ),
            (
                "closed job is hidden",
                "get",
                lambda: reverse("job-update", args=[self.closed_job.pk]),
                None,
                "json",
                {"anon": (404, nf), "cand": (404, nf), "emp2": (404, nf)},
            ),
            (
                "resumes list",
                "get",
                lambda: reverse("resumes"),
                None,
                "json",
                {"anon": (401, n), "emp1": (403, p), "cand": (200, None)},
            ),
            (
                "resume upload without a file",
                "post",
                lambda: reverse("resumes"),
                lambda: {},
                "multipart",
                {"anon": (401, n), "emp1": (403, p), "cand": (400, v)},
            ),
            (
                "applications list",
                "get",
                lambda: reverse("applications"),
                None,
                "json",
                {"anon": (401, n), "cand": (200, None), "emp1": (200, None)},
            ),
            (
                "apply as employer",
                "post",
                lambda: reverse("applications"),
                lambda: {"job": self.job.pk, "resume": self.resume.pk},
                "json",
                {"anon": (401, n), "emp1": (403, p)},
            ),
            (
                "apply with someone else's resume",
                "post",
                lambda: reverse("applications"),
                lambda: {"job": self.new_job().pk, "resume": self.resume2.pk},
                "json",
                {"cand": (400, "invalid_resume")},
            ),
            (
                "apply to a closed job",
                "post",
                lambda: reverse("applications"),
                lambda: {"job": self.closed_job.pk, "resume": self.resume.pk},
                "json",
                {"cand": (400, "job_closed")},
            ),
            (
                "apply twice",
                "post",
                lambda: reverse("applications"),
                lambda: {"job": self.job.pk, "resume": self.resume.pk},
                "json",
                {"cand": (400, "duplicate_application")},
            ),
            (
                "application detail",
                "get",
                lambda: reverse("application-detail", args=[self.app.pk]),
                None,
                "json",
                {
                    "anon": (401, n),
                    "cand": (200, None),
                    "emp1": (200, None),
                    "cand2": (404, nf),
                    "emp2": (404, nf),
                },
            ),
            (
                "application status change",
                "patch",
                lambda: reverse("application-status", args=[self.app.pk]),
                lambda: {"status": "reviewing"},
                "json",
                {
                    "anon": (401, n),
                    "cand": (403, p),
                    "cand2": (403, p),
                    "emp2": (404, nf),
                    "emp1": (200, None),
                },
            ),
            (
                "application status with an invalid value",
                "patch",
                lambda: reverse("application-status", args=[self.app.pk]),
                lambda: {"status": "banana"},
                "json",
                {"emp1": (400, v)},
            ),
            (
                "notifications",
                "get",
                lambda: reverse("notifications"),
                None,
                "json",
                {"anon": (401, n), "cand": (403, p), "emp1": (200, None)},
            ),
        ]

    def test_every_actor_gets_the_expected_status_and_envelope(self):
        for label, method, url_fn, data_fn, fmt, expected in self.rows():
            for actor, (status, code) in expected.items():
                with self.subTest(endpoint=label, actor=actor):
                    # fresh state each time: rebuild the world pieces that mutate
                    self.app.refresh_from_db()
                    if label == "application status change" and actor == "emp1":
                        Application.objects.filter(pk=self.app.pk).update(
                            status="applied"
                        )
                    data = data_fn() if data_fn else None
                    response = self.call(actor, method, url_fn(), data, fmt)
                    if status >= 400:
                        self.assert_envelope(response, status, code)
                    else:
                        self.assertEqual(
                            response.status_code, status, response.content[:400]
                        )
                        self.assertNotIn("error", response.json())

    def test_lists_are_scoped_to_the_caller(self):
        def ids(actor, url):
            return [row["id"] for row in self.call(actor, "get", url).json()["results"]]

        self.assertEqual(ids("cand", reverse("resumes")), [self.resume.pk])
        self.assertEqual(ids("cand2", reverse("resumes")), [self.resume2.pk])
        self.assertEqual(ids("cand", reverse("applications")), [self.app.pk])
        self.assertEqual(ids("cand2", reverse("applications")), [])
        self.assertEqual(ids("emp1", reverse("applications")), [self.app.pk])
        self.assertEqual(ids("emp2", reverse("applications")), [])

    def test_non_owner_cannot_change_or_close_the_job(self):
        job = self.new_job()
        self.call(
            "emp2", "patch", reverse("job-update", args=[job.pk]), {"title": "Hacked"}
        )
        self.call("emp2", "post", reverse("job-close", args=[job.pk]))
        job.refresh_from_db()
        self.assertEqual(job.title, "Backend Engineer")
        self.assertTrue(job.is_open)

    def test_non_owner_cannot_change_application_status(self):
        self.call(
            "emp2",
            "patch",
            reverse("application-status", args=[self.app.pk]),
            {"status": "hired"},
        )
        self.call(
            "cand",
            "patch",
            reverse("application-status", args=[self.app.pk]),
            {"status": "hired"},
        )
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "applied")

    def test_body_cannot_reassign_job_company_or_reopen(self):
        r = self.call(
            "emp1",
            "patch",
            reverse("job-update", args=[self.closed_job.pk]),
            {"company": self.company2.pk, "is_open": True},
        )
        self.closed_job.refresh_from_db()
        self.assertEqual(self.closed_job.company_id, self.company1.pk)
        self.assertFalse(self.closed_job.is_open)
        self.assertLess(r.status_code, 500)


# -------------------------------------------------------- 405 / 404 / 400 / 401


class ErrorShapeTests(World):
    def test_405_uses_the_envelope(self):
        for actor, method, url in (
            ("emp1", "delete", reverse("company")),
            ("emp1", "patch", reverse("me")),
            ("emp1", "get", reverse("application-status", args=[self.app.pk])),
            ("emp1", "delete", reverse("job-update", args=[self.job.pk])),
        ):
            with self.subTest(method=method, url=url):
                r = self.call(actor, method, url)
                self.assert_envelope(r, 405, "method_not_allowed")
        self.assertTrue(Company.objects.filter(owner=self.emp1).exists())
        self.assertTrue(Job.objects.filter(pk=self.job.pk).exists())

    def test_unknown_urls_are_json_404(self):
        for path in (
            "/api/does-not-exist/",
            "/api/jobs/abc/",
            "/nope",
            "/api/jobs/1/close/x/",
        ):
            for actor in ("anon", "emp1"):
                with self.subTest(path=path, actor=actor):
                    self.assert_envelope(
                        self.call(actor, "get", path), 404, "not_found"
                    )

    def test_malformed_json_bodies_are_400(self):
        self.client.force_authenticate(user=self.emp1)
        for url in (reverse("company"), reverse("job-create")):
            for body in ("{bad json", "[]", "null", '"text"'):
                with self.subTest(url=url, body=body):
                    r = self.client.post(url, body, content_type="application/json")
                    self.assert_envelope(r, 400, "validation_error")

    def test_validation_errors_do_not_leak_internals(self):
        r = self.call(
            "emp1", "post", reverse("job-create"), {"min_years_experience": 2**31}
        )
        self.assert_envelope(r, 400, "validation_error")
        r = self.call(
            "emp1", "post", reverse("job-create"), dict(JOB_BODY, title="x" * 100000)
        )
        self.assertLess(r.status_code, 500)


class TokenFailureTests(World):
    def get_me(self, token):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=token)
        return self.client.get(reverse("me"))

    def test_bad_authorization_headers_are_401(self):
        for header in (
            "Bearer",
            "Bearer garbage",
            "Bearer a.b.c",
            "Token abc",
            "Basic Zm9vOmJhcg==",
            "",
        ):
            with self.subTest(header=header):
                self.assert_envelope(self.get_me(header), 401, "not_authenticated")

    def test_expired_token_is_401(self):
        token = AccessToken.for_user(self.cand)
        token.set_exp(lifetime=-timedelta(seconds=5))
        self.assert_envelope(self.get_me(f"Bearer {token}"), 401, "not_authenticated")

    def test_refresh_token_is_not_accepted_as_access_token(self):
        refresh = RefreshToken.for_user(self.cand)
        self.assert_envelope(self.get_me(f"Bearer {refresh}"), 401, "not_authenticated")

    def test_token_of_a_deleted_user_is_401(self):
        token = AccessToken.for_user(self.cand2)
        self.cand2.delete()
        self.assert_envelope(self.get_me(f"Bearer {token}"), 401, "not_authenticated")

    def test_token_of_a_deactivated_user_is_401(self):
        token = AccessToken.for_user(self.cand2)
        User.objects.filter(pk=self.cand2.pk).update(is_active=False)
        self.assert_envelope(self.get_me(f"Bearer {token}"), 401, "not_authenticated")

    def test_wrong_password_and_unknown_user_look_the_same(self):
        self.cand.set_password(PASSWORD)
        self.cand.save()
        bad = self.client.post(
            reverse("login"), {"username": "cand", "password": "nope"}, format="json"
        )
        ghost = self.client.post(
            reverse("login"), {"username": "ghost", "password": "nope"}, format="json"
        )
        self.assert_envelope(bad, 401)
        self.assert_envelope(ghost, 401)
        self.assertEqual(bad.json(), ghost.json())
        self.assertNotIn("access", bad.json())


# ------------------------------------------------------ consolidation guards


class ConsolidationTests(World):
    def test_role_permissions_check_the_role_and_fail_closed(self):
        from accounts.permissions import IsCandidate, IsEmployer

        def request_for(user):
            return SimpleNamespace(user=user)

        cases = [
            (IsEmployer, self.emp1, True),
            (IsEmployer, self.cand, False),
            (IsEmployer, AnonymousUser(), False),
            (IsEmployer, SimpleNamespace(is_authenticated=True, role=None), False),
            (IsEmployer, SimpleNamespace(is_authenticated=True, role="admin"), False),
            (IsCandidate, self.cand, True),
            (IsCandidate, self.emp1, False),
            (IsCandidate, AnonymousUser(), False),
            (IsCandidate, SimpleNamespace(is_authenticated=True), False),
        ]
        for permission, user, allowed in cases:
            with self.subTest(permission=permission.__name__, user=str(user)):
                self.assertIs(
                    bool(permission().has_permission(request_for(user), None)), allowed
                )

    def test_staff_or_superuser_flags_do_not_grant_a_business_role(self):
        boss = User.objects.create(
            username="boss",
            email="boss@example.com",
            role="candidate",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_authenticate(user=boss)
        r = self.client.post(
            reverse("company"), {"name": "B", "description": "d"}, format="json"
        )
        self.assert_envelope(r, 403, "permission_denied")

    def test_no_hand_built_error_responses_remain_in_app_code(self):
        base = Path(settings.BASE_DIR)
        offenders = []
        for app in ("accounts", "jobs", "applications"):
            for path in (base / app).rglob("*.py"):
                if (
                    "migrations" in path.parts
                    or path.name.startswith("test")
                    or path.name == "resume_files.py"
                ):
                    continue
                text = path.read_text(encoding="utf-8")
                if re.search(r"""["']error["']\s*:""", text) or "JsonResponse(" in text:
                    offenders.append(str(path.relative_to(base)))
        self.assertEqual(
            offenders, [], "build errors with DRF exceptions + the shared handler"
        )

    def test_exception_handler_is_wired_in_settings(self):
        self.assertEqual(
            settings.REST_FRAMEWORK["EXCEPTION_HANDLER"],
            "config.exceptions.exception_handler",
        )
