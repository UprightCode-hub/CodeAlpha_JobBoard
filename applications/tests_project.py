"""Task 6 tests. Copy to applications/tests_project.py in the repo. Agents must not edit it.
They check the project as a whole: admin, demo data, API docs, the list of URLs, and the docs files."""
import io
import re
from contextlib import redirect_stdout

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import get_resolver, reverse

from applications.models import Application, Notification, Resume
from jobs.models import Company, Job

User = get_user_model()
BASE = settings.BASE_DIR

# Every route the project may expose. Admin routes are ignored, Django generates those.
CONTRACT_ROUTES = {
    "api/auth/register/",
    "api/auth/login/",
    "api/auth/me/",
    "api/company/",
    "api/jobs/",
    "api/jobs/<int:pk>/",
    "api/jobs/<int:pk>/close/",
    "api/my/jobs/",
    "api/resumes/",
    "api/applications/",
    "api/applications/<int:pk>/",
    "api/applications/<int:pk>/status/",
    "api/notifications/",
}
DOC_ROUTES = {"api/schema/", "api/docs/"}

MODELS = [User, Company, Job, Resume, Application, Notification]


def collect_routes(patterns, prefix=""):
    routes = []
    for p in patterns:
        if hasattr(p, "url_patterns"):
            routes.extend(collect_routes(p.url_patterns, prefix + str(p.pattern)))
        else:
            routes.append(prefix + str(p.pattern))
    return routes


def read(name):
    path = BASE / name
    return path.read_text(encoding="utf-8")


def run_seed():
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        call_command("seed_demo", stdout=buffer)
    return buffer.getvalue()


class AdminTests(TestCase):
    def test_every_model_is_registered_with_useful_columns_and_search(self):
        for model in MODELS:
            with self.subTest(model=model.__name__):
                self.assertIn(model, admin.site._registry)
                model_admin = admin.site._registry[model]
                self.assertGreater(len(model_admin.list_display), 1)
                self.assertTrue(model_admin.search_fields)

    def test_admin_list_pages_and_search_load_for_a_superuser(self):
        boss = User.objects.create(
            username="boss", email="boss@example.com", role="employer",
            is_staff=True, is_superuser=True,
        )
        self.client.force_login(boss)
        for model in MODELS:
            name = f"admin:{model._meta.app_label}_{model._meta.model_name}_changelist"
            with self.subTest(model=model.__name__):
                url = reverse(name)
                self.assertEqual(self.client.get(url).status_code, 200)
                self.assertEqual(self.client.get(url, {"q": "a"}).status_code, 200)


class SeedDemoTests(TestCase):
    def test_creates_the_demo_data_from_the_task(self):
        out = run_seed()
        self.assertEqual(User.objects.filter(role="employer").count(), 1)
        self.assertEqual(User.objects.filter(role="candidate").count(), 1)
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 3)
        self.assertEqual(Job.objects.filter(is_open=True).count(), 3)
        employer = User.objects.get(role="employer")
        candidate = User.objects.get(role="candidate")
        self.assertEqual(Company.objects.get().owner, employer)
        self.assertTrue(employer.has_usable_password())
        self.assertTrue(candidate.has_usable_password())
        self.assertIn(employer.username, out)
        self.assertIn(candidate.username, out)
        self.assertIn("password", out.lower())

    def test_the_three_jobs_differ_in_their_filters(self):
        run_seed()
        combos = {(j.job_type, j.work_model, j.experience_level) for j in Job.objects.all()}
        self.assertEqual(len(combos), 3)

    def test_seeded_jobs_follow_the_contract_rules(self):
        run_seed()
        for job in Job.objects.all():
            self.assertGreaterEqual(job.min_years_experience, 0)
            if job.salary_min is not None and job.salary_max is not None:
                self.assertLessEqual(job.salary_min, job.salary_max)
            if job.salary_min is not None:
                self.assertGreaterEqual(job.salary_min, 0)

    def test_running_twice_creates_no_duplicates(self):
        run_seed()
        run_seed()
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(Company.objects.count(), 1)
        self.assertEqual(Job.objects.count(), 3)

    def test_creates_no_resumes_applications_or_notifications(self):
        run_seed()
        self.assertEqual(Resume.objects.count(), 0)
        self.assertEqual(Application.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_seeded_jobs_show_up_in_the_public_list(self):
        run_seed()
        r = self.client.get("/api/jobs/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 3)


class ApiDocsTests(TestCase):
    def test_spectacular_is_configured(self):
        self.assertIn("drf_spectacular", settings.INSTALLED_APPS)
        self.assertEqual(
            settings.REST_FRAMEWORK["DEFAULT_SCHEMA_CLASS"],
            "drf_spectacular.openapi.AutoSchema",
        )

    def test_schema_returns_200(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)

    def test_swagger_page_returns_200(self):
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)

    def test_schema_lists_every_contract_endpoint(self):
        r = self.client.get("/api/schema/", {"format": "json"})
        self.assertEqual(r.status_code, 200)
        wanted = {"/" + route for route in CONTRACT_ROUTES}
        wanted = {re.sub(r"<int:pk>", "{}", p) for p in wanted}
        got = {re.sub(r"\{[^}]+\}", "{}", p) for p in r.json()["paths"]}
        self.assertTrue(wanted.issubset(got), f"missing from schema: {sorted(wanted - got)}")


class EndpointInventoryTests(TestCase):
    def test_project_exposes_only_contract_routes_and_the_two_doc_routes(self):
        routes = collect_routes(get_resolver().url_patterns)
        outside_admin = {r for r in routes if not r.startswith("admin/")}
        self.assertEqual(outside_admin, CONTRACT_ROUTES | DOC_ROUTES)


class DocsFilesTests(TestCase):
    def test_env_example_has_the_variable_names_and_no_dashes(self):
        text = read(".env.example")
        for name in ["SECRET_KEY", "DEBUG", "DB_NAME", "DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT"]:
            self.assertRegex(text, rf"(?m)^{name}=")
        self.assertNotIn("\u2014", text)

    def test_readme_has_both_diagrams_and_the_required_parts(self):
        text = read("README.md")
        self.assertNotIn("\u2014", text)
        self.assertGreaterEqual(text.count("```mermaid"), 2)
        self.assertIn("DECISIONS.md", text)
        self.assertIn("seed_demo", text)
        self.assertIn("/api/docs/", text)
        self.assertIn("manage.py test", text)
        self.assertIn("erDiagram", text)
        self.assertTrue(any(word in text for word in ("flowchart", "sequenceDiagram", "graph TD", "graph LR")))
        start = text.index("erDiagram")
        end = text.find("```", start)
        er_block = text[start:end]
        for name in ["User", "Company", "Job", "Resume", "Application", "Notification"]:
            self.assertIn(name, er_block)

    def test_decisions_has_the_required_sections(self):
        text = read("DECISIONS.md")
        self.assertIn("Not covered by tests", text)
        self.assertIn("simultaneous", text.lower())
        self.assertIn("dropped connections", text.lower())
        self.assertIn("database down", text.lower())
        self.assertIn("If this grew 10x", text)
        self.assertIn("WISDOM TO CONFIRM:", text)