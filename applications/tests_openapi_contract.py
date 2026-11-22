"""OpenAPI contract: zero warnings and no drift from serializer/security rules.

Drop into applications/. Run: python manage.py test applications.tests_openapi_contract
"""

import os
import re
import subprocess
import sys
import tempfile
from typing import Any

import yaml
from django.conf import settings
from django.test import TestCase
from django.urls import reverse

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

# Operations that are allowed to be public (no jwtAuth in the schema).
PUBLIC_OPERATIONS = {
    ("post", "/api/auth/register/"),
    ("post", "/api/auth/login/"),
    ("get", "/api/jobs/"),
    ("get", "/api/jobs/{id}/"),
}

EXPECTED_OPERATIONS = {
    ("post", "/api/auth/register/"),
    ("post", "/api/auth/login/"),
    ("get", "/api/auth/me/"),
    ("get", "/api/company/"),
    ("post", "/api/company/"),
    ("patch", "/api/company/"),
    ("get", "/api/jobs/"),
    ("post", "/api/jobs/"),
    ("get", "/api/jobs/{id}/"),
    ("patch", "/api/jobs/{id}/"),
    ("post", "/api/jobs/{id}/close/"),
    ("get", "/api/my/jobs/"),
    ("get", "/api/resumes/"),
    ("post", "/api/resumes/"),
    ("get", "/api/applications/"),
    ("post", "/api/applications/"),
    ("get", "/api/applications/{id}/"),
    ("patch", "/api/applications/{id}/status/"),
    ("get", "/api/notifications/"),
}

SERVER_CONTROLLED = {"id", "company", "owner", "is_open", "created_at", "company_name"}


def normalize(path):
    return re.sub(r"\{[^}]+\}", "{id}", path)


class SchemaBase(TestCase):
    schema: dict[str, Any]
    paths: dict[str, Any]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        response = cls.client_class().get(reverse("schema"))
        assert response.status_code == 200, response.status_code
        cls.schema = yaml.safe_load(response.content)
        cls.paths = {normalize(p): item for p, item in cls.schema["paths"].items()}

    # -- helpers
    def resolve(self, node):
        if "$ref" in node:
            target = self.schema
            for part in node["$ref"].lstrip("#/").split("/"):
                target = target[part]
            return self.resolve(target)
        if "allOf" in node:
            merged = {}
            for part in node["allOf"]:
                merged.update(self.resolve(part))
            merged.update({k: v for k, v in node.items() if k != "allOf"})
            return merged
        return node

    def op(self, path, method):
        return self.paths[path][method]

    def request_schema(self, path, method, content_type="application/json"):
        content = self.op(path, method)["requestBody"]["content"]
        return self.resolve(content[content_type]["schema"])

    def response_schema(self, path, method, code):
        content = self.op(path, method)["responses"][str(code)]["content"]
        return self.resolve(content["application/json"]["schema"])

    def props(self, schema):
        return set(self.resolve(schema).get("properties", {}))

    def operations(self):
        for path, item in self.paths.items():
            if path == "/api/schema/":
                continue
            for method in item:
                if method in HTTP_METHODS:
                    yield method, path, item[method]


class ValidationTests(TestCase):
    def test_spectacular_validate_fail_on_warn_exits_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "schema.yml")
            result = subprocess.run(
                [
                    sys.executable,
                    "manage.py",
                    "spectacular",
                    "--validate",
                    "--fail-on-warn",
                    "--file",
                    target,
                ],
                cwd=str(settings.BASE_DIR),
                capture_output=True,
                text=True,
                timeout=180,
            )
        report = (result.stdout + result.stderr)[-2500:]
        self.assertEqual(result.returncode, 0, report)
        self.assertNotRegex(result.stderr, r"(?i)warning|error:", report)

    def test_in_process_generation_records_no_warnings_or_errors(self):
        from drf_spectacular.drainage import GENERATOR_STATS
        from drf_spectacular.generators import SchemaGenerator

        GENERATOR_STATS.reset()
        SchemaGenerator().get_schema(request=None, public=True)
        details = {
            "warnings": dict(getattr(GENERATOR_STATS, "_warn_cache", {})),
            "errors": dict(getattr(GENERATOR_STATS, "_error_cache", {})),
        }
        self.assertFalse(GENERATOR_STATS, details)

    def test_schema_generation_is_deterministic(self):
        first = self.client.get(reverse("schema")).content
        second = self.client.get(reverse("schema")).content
        self.assertEqual(first, second)

    def test_docs_page_is_served(self):
        r = self.client.get(reverse("swagger-ui"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("swagger", r.content.decode().lower())


class CoverageAndSecurityTests(SchemaBase):
    def test_every_expected_operation_is_documented(self):
        documented = {(m, p) for m, p, _ in self.operations()}
        self.assertEqual(sorted(EXPECTED_OPERATIONS - documented), [])

    def test_no_undocumented_extra_operations_appear_silently(self):
        documented = {(m, p) for m, p, _ in self.operations()}
        extras = documented - EXPECTED_OPERATIONS
        # Add a deliberate new endpoint to EXPECTED_OPERATIONS when you create one.
        self.assertEqual(sorted(extras), [])

    def test_every_operation_has_a_unique_operation_id(self):
        ids = [op["operationId"] for _, _, op in self.operations()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_only_the_expected_operations_are_public(self):
        public = {
            (m, p)
            for m, p, op in self.operations()
            if not any("jwtAuth" in entry for entry in op.get("security", []))
        }
        self.assertEqual(sorted(public - PUBLIC_OPERATIONS), [])

    def test_secured_operations_reject_anonymous_requests(self):
        for method, path, _op in self.operations():
            if (method, path) in PUBLIC_OPERATIONS:
                continue
            with self.subTest(op=f"{method.upper()} {path}"):
                r = self.client.generic(method.upper(), path.replace("{id}", "1"))
                self.assertEqual(r.status_code, 401, r.content[:200])
                self.assertEqual(r.json()["error"]["code"], "not_authenticated")

    def test_public_operations_do_not_demand_credentials(self):
        for method, path in PUBLIC_OPERATIONS:
            with self.subTest(op=f"{method.upper()} {path}"):
                r = self.client.generic(method.upper(), path.replace("{id}", "999999"))
                self.assertNotIn(r.status_code, (401, 403))

    def test_jwt_bearer_scheme_is_declared(self):
        scheme = self.schema["components"]["securitySchemes"]["jwtAuth"]
        self.assertEqual((scheme["type"], scheme["scheme"]), ("http", "bearer"))


class ContractShapeTests(SchemaBase):
    def test_register_request_has_no_role_and_response_has_read_only_role(self):
        request = self.request_schema("/api/auth/register/", "post")
        self.assertEqual(self.props(request), {"username", "email", "password"})
        response = self.response_schema("/api/auth/register/", "post", 201)
        self.assertEqual(self.props(response), {"id", "username", "email", "role"})
        self.assertTrue(self.resolve(response["properties"]["role"]).get("readOnly"))

    def test_token_response_shape(self):
        response = self.response_schema("/api/auth/login/", "post", 200)
        self.assertEqual(self.props(response), {"access", "refresh"})

    def test_me_response_shape(self):
        response = self.response_schema("/api/auth/me/", "get", 200)
        self.assertEqual(self.props(response), {"id", "username", "email", "role"})

    def test_company_schemas_hide_the_owner(self):
        request = self.request_schema("/api/company/", "post")
        self.assertEqual(self.props(request), {"name", "description"})
        for method, code in (("post", 201), ("get", 200), ("patch", 200)):
            with self.subTest(method=method):
                response = self.response_schema("/api/company/", method, code)
                self.assertEqual(self.props(response), {"id", "name", "description"})

    def test_job_request_cannot_set_server_controlled_fields(self):
        for method, path in (("post", "/api/jobs/"), ("patch", "/api/jobs/{id}/")):
            with self.subTest(op=f"{method} {path}"):
                request = self.request_schema(path, method)
                self.assertEqual(self.props(request) & SERVER_CONTROLLED, set())

    def test_job_write_and_read_responses_share_one_shape(self):
        shapes = {
            self.response_shape("/api/jobs/", "post", 201),
            self.response_shape("/api/jobs/{id}/", "patch", 200),
            self.response_shape("/api/jobs/{id}/", "get", 200),
            self.response_shape("/api/jobs/{id}/close/", "post", 200),
        }
        self.assertEqual(len(shapes), 1, shapes)
        self.assertIn("company_name", next(iter(shapes)))

    def response_shape(self, path, method, code):
        return frozenset(self.props(self.response_schema(path, method, code)))

    def test_resume_upload_is_multipart_only_with_a_binary_file(self):
        content = self.op("/api/resumes/", "post")["requestBody"]["content"]
        self.assertEqual(set(content), {"multipart/form-data"})
        schema = self.request_schema("/api/resumes/", "post", "multipart/form-data")
        self.assertEqual(self.props(schema), {"title", "file"})
        self.assertEqual(
            self.resolve(schema["properties"]["file"]).get("format"), "binary"
        )
        self.assertEqual(set(schema["required"]), {"title", "file"})

    def test_resume_response_never_contains_a_file_url(self):
        response = self.response_schema("/api/resumes/", "post", 201)
        self.assertEqual(
            self.props(response), {"id", "title", "file_name", "uploaded_at"}
        )

    def test_apply_and_status_requests_are_minimal(self):
        apply_request = self.request_schema("/api/applications/", "post")
        self.assertEqual(self.props(apply_request), {"job", "resume"})
        status_request = self.request_schema("/api/applications/{id}/status/", "patch")
        self.assertEqual(self.props(status_request), {"status"})
        enum = self.resolve(status_request["properties"]["status"])["enum"]
        self.assertEqual(
            enum, ["applied", "reviewing", "shortlisted", "rejected", "hired"]
        )

    def test_list_endpoints_are_documented_as_paginated(self):
        for path in ("/api/applications/", "/api/resumes/", "/api/notifications/"):
            with self.subTest(path=path):
                response = self.response_schema(path, "get", 200)
                self.assertEqual(
                    self.props(response), {"count", "next", "previous", "results"}
                )


class SerializerDriftTests(SchemaBase):
    """The schema must be derived from the real serializer classes, not a copy."""

    def writable(self, serializer):
        return {n for n, f in serializer.fields.items() if not f.read_only}

    def readable(self, serializer):
        return {n for n, f in serializer.fields.items() if not f.write_only}

    def test_register_serializer(self):
        from accounts.serializers import RegisterSerializer

        s = RegisterSerializer()
        request = self.request_schema("/api/auth/register/", "post")
        self.assertEqual(self.props(request), self.writable(s))
        response = self.response_schema("/api/auth/register/", "post", 201)
        self.assertEqual(self.props(response), self.readable(s))

    def test_user_serializer(self):
        from accounts.serializers import UserSerializer

        response = self.response_schema("/api/auth/me/", "get", 200)
        self.assertEqual(self.props(response), self.readable(UserSerializer()))

    def test_company_serializers(self):
        from jobs.serializers import CompanyReadSerializer, CompanySerializer

        request = self.request_schema("/api/company/", "post")
        self.assertEqual(self.props(request), self.writable(CompanySerializer()))
        response = self.response_schema("/api/company/", "get", 200)
        self.assertEqual(self.props(response), self.readable(CompanyReadSerializer()))

    def test_job_serializer(self):
        from jobs.serializers import JobReadSerializer, JobSerializer

        s = JobSerializer()
        request = self.request_schema("/api/jobs/", "post")
        self.assertEqual(self.props(request), self.writable(s))
        response = self.response_schema("/api/jobs/", "post", 201)
        self.assertEqual(self.props(response), self.readable(JobReadSerializer()))

    def test_resume_upload_serializer(self):
        from applications.serializers import ResumeUploadSerializer

        schema = self.request_schema("/api/resumes/", "post", "multipart/form-data")
        self.assertEqual(self.props(schema), self.writable(ResumeUploadSerializer()))

    def test_job_choice_values_match_the_model(self):
        from jobs.models import Job

        request = self.request_schema("/api/jobs/", "post")
        for field in ("job_type", "work_model", "experience_level"):
            with self.subTest(field=field):
                enum = self.resolve(request["properties"][field])["enum"]
                model_values = [
                    value
                    for value, _ in Job._meta.get_field(field).choices  # type: ignore[union-attr]
                ]
                self.assertEqual(enum, model_values)
