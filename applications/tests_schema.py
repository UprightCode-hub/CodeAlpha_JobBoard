"""Task 7 tests. Copy to applications/tests_schema.py in the repo. Agents must not edit it.
They read the generated OpenAPI schema (the data behind the Swagger page) and check that it
describes the requests, query parameters and responses that the contract defines."""
import re

from django.test import TestCase

JOB_FIELDS = {
    "id", "title", "description", "location", "job_type", "work_model",
    "experience_level", "min_years_experience", "salary_min", "salary_max",
    "is_open", "created_at", "company_name",
}
JOB_WRITE_FIELDS = {
    "title", "description", "location", "job_type", "work_model",
    "experience_level", "min_years_experience", "salary_min", "salary_max",
}
RESUME_FIELDS = {"id", "title", "file_name", "uploaded_at"}
APPLICATION_FIELDS = {
    "id", "job", "job_title", "company_name", "candidate_username",
    "resume", "status", "applied_at", "updated_at",
}
NOTIFICATION_FIELDS = {"id", "message", "application", "is_read", "created_at"}
LIST_KEYS = {"count", "next", "previous", "results"}
STATUSES = {"applied", "reviewing", "shortlisted", "rejected", "hired"}

FILTER_ENUMS = {
    "job_type": {"full_time", "part_time", "contract", "internship"},
    "work_model": {"remote", "hybrid", "onsite"},
    "experience_level": {"entry", "mid", "senior"},
}
FILTER_PARAMS = {
    "q", "location", "job_type", "work_model", "experience_level",
    "min_salary", "posted_within_days", "page",
}

# (path, method, success code, "list" or "object", exact fields or None)
RESPONSES = [
    ("/api/jobs/", "get", "200", "list", JOB_FIELDS),
    ("/api/my/jobs/", "get", "200", "list", JOB_FIELDS),
    ("/api/jobs/", "post", "201", "object", JOB_FIELDS),
    ("/api/jobs/{}/", "get", "200", "object", JOB_FIELDS),
    ("/api/jobs/{}/", "patch", "200", "object", JOB_FIELDS),
    ("/api/jobs/{}/close/", "post", "200", "object", JOB_FIELDS),
    ("/api/resumes/", "get", "200", "list", RESUME_FIELDS),
    ("/api/resumes/", "post", "201", "object", RESUME_FIELDS),
    ("/api/applications/", "get", "200", "list", APPLICATION_FIELDS),
    ("/api/applications/", "post", "201", "object", APPLICATION_FIELDS),
    ("/api/applications/{}/", "get", "200", "object", APPLICATION_FIELDS),
    ("/api/applications/{}/status/", "patch", "200", "object", APPLICATION_FIELDS),
    ("/api/notifications/", "get", "200", "list", NOTIFICATION_FIELDS),
    ("/api/company/", "get", "200", "object", None),
    ("/api/company/", "post", "201", "object", None),
    ("/api/company/", "patch", "200", "object", None),
]


def normalize(path):
    return re.sub(r"\{[^}]+\}", "{}", path)


class SchemaTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schema = None

    def setUp(self):
        r = self.client.get("/api/schema/", {"format": "json"})
        self.assertEqual(r.status_code, 200)
        self.schema = r.json()
        self.ops = {}
        for path, item in self.schema["paths"].items():
            for method, operation in item.items():
                if method in {"get", "post", "put", "patch", "delete"}:
                    self.ops[(normalize(path), method)] = operation

    # helpers
    def resolve(self, node):
        while True:
            if "$ref" in node:
                name = node["$ref"].split("/")[-1]
                node = self.schema["components"]["schemas"][name]
            elif "allOf" in node and len(node["allOf"]) == 1:
                node = node["allOf"][0]
            else:
                return node

    def op(self, path, method):
        self.assertIn((path, method), self.ops, f"{method.upper()} {path} is missing from the schema")
        return self.ops[(path, method)]

    def request_props(self, path, method, content_type="application/json"):
        operation = self.op(path, method)
        self.assertIn("requestBody", operation, f"{method.upper()} {path} has no request body")
        content = operation["requestBody"]["content"]
        self.assertIn(content_type, content)
        return self.resolve(content[content_type]["schema"]).get("properties", {})

    def response_schema(self, path, method, code):
        operation = self.op(path, method)
        self.assertIn(code, operation["responses"])
        response = operation["responses"][code]
        self.assertIn("content", response, f"{method.upper()} {path} {code} has no response body")
        return self.resolve(response["content"]["application/json"]["schema"])

    def query_params(self, path, method):
        params = {}
        for p in self.op(path, method).get("parameters", []):
            if p["in"] == "query":
                params[p["name"]] = p
        return params

    # request bodies
    def test_job_create_and_update_bodies(self):
        for method, path in [("post", "/api/jobs/"), ("patch", "/api/jobs/{}/")]:
            with self.subTest(method=method, path=path):
                props = set(self.request_props(path, method))
                self.assertTrue(JOB_WRITE_FIELDS.issubset(props), f"missing: {sorted(JOB_WRITE_FIELDS - props)}")
                for forbidden in ("is_open", "company", "owner", "id", "created_at", "company_name"):
                    self.assertNotIn(forbidden, props)

    def test_company_bodies(self):
        for method in ("post", "patch"):
            with self.subTest(method=method):
                props = set(self.request_props("/api/company/", method))
                self.assertTrue({"name", "description"}.issubset(props))
                self.assertNotIn("owner", props)

    def test_resume_upload_is_documented_as_multipart_with_a_file(self):
        props = self.request_props("/api/resumes/", "post", "multipart/form-data")
        self.assertEqual(set(props), {"title", "file"})
        self.assertEqual(self.resolve(props["file"]).get("format"), "binary")

    def test_apply_body_is_job_and_resume_only(self):
        props = self.request_props("/api/applications/", "post")
        self.assertEqual(set(props), {"job", "resume"})

    def test_status_body_lists_the_five_statuses(self):
        props = self.request_props("/api/applications/{}/status/", "patch")
        self.assertEqual(set(props), {"status"})
        self.assertEqual(set(self.resolve(props["status"]).get("enum", [])), STATUSES)

    def test_close_has_no_request_body(self):
        self.assertNotIn("requestBody", self.op("/api/jobs/{}/close/", "post"))

    # query parameters
    def test_job_list_documents_every_filter_and_page(self):
        params = self.query_params("/api/jobs/", "get")
        self.assertTrue(FILTER_PARAMS.issubset(params), f"missing: {sorted(FILTER_PARAMS - set(params))}")
        for name, values in FILTER_ENUMS.items():
            with self.subTest(param=name):
                self.assertEqual(set(self.resolve(params[name]["schema"]).get("enum", [])), values)

    def test_other_lists_document_page(self):
        for path in ["/api/my/jobs/", "/api/resumes/", "/api/applications/", "/api/notifications/"]:
            with self.subTest(path=path):
                self.assertIn("page", self.query_params(path, "get"))

    # responses
    def test_responses_describe_the_contract_fields(self):
        for path, method, code, kind, fields in RESPONSES:
            with self.subTest(path=path, method=method):
                body = self.response_schema(path, method, code)
                if kind == "list":
                    self.assertEqual(set(body["properties"]), LIST_KEYS)
                    items = self.resolve(body["properties"]["results"]["items"])
                    props = set(items["properties"])
                else:
                    props = set(body["properties"])
                if fields is not None:
                    self.assertEqual(props, fields)
                else:
                    self.assertTrue({"name", "description"}.issubset(props))
                    self.assertNotIn("owner", props)

    # general
    def test_operation_ids_are_unique_without_number_suffixes(self):
        ids = [op["operationId"] for op in self.ops.values()]
        self.assertEqual(len(ids), len(set(ids)))
        for operation_id in ids:
            self.assertIsNone(re.search(r"_\d+$", operation_id), operation_id)

    def test_schema_has_a_title(self):
        self.assertEqual(self.schema["info"]["title"], "CodeAlpha Job Board API")