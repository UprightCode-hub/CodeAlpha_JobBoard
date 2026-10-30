"""Task 5 tests. Copy to applications/tests_api.py in the repo. Agents must not edit it.
They use the ORM to set up data, so they do not depend on the Task 3 read endpoints."""
import shutil
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.query import QuerySet
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from applications.models import Application, Notification, Resume
from jobs.models import Company, Job

User = get_user_model()

RESUMES = "/api/resumes/"
APPLICATIONS = "/api/applications/"
NOTIFICATIONS = "/api/notifications/"
MAX_BYTES = 2 * 1024 * 1024

RESUME_FIELDS = {"id", "title", "file_name", "uploaded_at"}
APPLICATION_FIELDS = {
    "id", "job", "job_title", "company_name", "candidate_username",
    "resume", "status", "applied_at", "updated_at",
}
NOTIFICATION_FIELDS = {"id", "message", "application", "is_read", "created_at"}
LIST_KEYS = {"count", "next", "previous", "results"}

ALLOWED_MOVES = {
    "applied": {"reviewing", "rejected"},
    "reviewing": {"shortlisted", "rejected"},
    "shortlisted": {"hired", "rejected"},
    "hired": set(),
    "rejected": set(),
}
ALL_STATUSES = list(ALLOWED_MOVES)


def make_user(username, role):
    # No password hashing: these tests log in with force_authenticate, and hashing is slow.
    return User.objects.create(username=username, email=f"{username}@example.com", role=role)


def pdf(name="cv.pdf", content=b"%PDF-1.4\nfake body\n"):
    return SimpleUploadedFile(name, content, content_type="application/pdf")


def docx(name="cv.docx", content=b"PK\x03\x04" + b"\x00" * 50):
    return SimpleUploadedFile(name, content, content_type="application/octet-stream")


class Base(APITestCase):
    def setUp(self):
        media = tempfile.mkdtemp()
        self.media = media
        override = override_settings(MEDIA_ROOT=media)
        override.enable()
        self.addCleanup(override.disable)
        self.addCleanup(shutil.rmtree, media, ignore_errors=True)

        self.emp1 = make_user("emp1", "employer")
        self.emp2 = make_user("emp2", "employer")
        self.cand = make_user("cand", "candidate")
        self.cand2 = make_user("cand2", "candidate")
        self.company1 = Company.objects.create(owner=self.emp1, name="Acme", description="d")
        self.company2 = Company.objects.create(owner=self.emp2, name="Globex", description="d")
        self.job = self.make_job()
        self.resume = self.make_resume(self.cand)

    def login(self, user):
        self.client.force_authenticate(user=user)

    def make_job(self, company=None, title="Backend Engineer", is_open=True):
        return Job.objects.create(
            company=company or self.company1,
            title=title,
            description="Build APIs",
            location="Lagos",
            job_type="full_time",
            work_model="remote",
            experience_level="mid",
            min_years_experience=2,
            is_open=is_open,
        )

    def make_resume(self, owner, title="CV"):
        return Resume.objects.create(candidate=owner, title=title, file="resumes/cv.pdf")

    def make_app(self, candidate=None, job=None, resume=None, status="applied"):
        candidate = candidate or self.cand
        return Application.objects.create(
            candidate=candidate,
            job=job or self.job,
            resume=resume or Resume.objects.filter(candidate=candidate).first() or self.make_resume(candidate),
            status=status,
        )

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(body["error"]["code"], code)
        self.assertTrue(body["error"]["message"].strip())

    def assert_list_shape(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json().keys()), LIST_KEYS)

    def stored_files(self):
        import os
        found = []
        for _root, _dirs, files in os.walk(self.media):
            found.extend(files)
        return found

    def apply(self, job=None, resume=None):
        return self.client.post(
            APPLICATIONS,
            {"job": (job or self.job).id, "resume": (resume or self.resume).id},
            format="json",
        )

    def assert_no_application_or_notification(self):
        self.assertEqual(Application.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)


# ---------------------------------------------------------------- resumes

class ResumeUploadTests(Base):
    def upload(self, file=None, title="My CV", **extra):
        data = {"title": title}
        if file is not None:
            data["file"] = file
        data.update(extra)
        return self.client.post(RESUMES, data, format="multipart")

    def test_candidate_uploads_pdf(self):
        self.login(self.cand2)
        r = self.upload(pdf("my_cv.pdf"))
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(set(body.keys()), RESUME_FIELDS)
        self.assertEqual(body["title"], "My CV")
        self.assertEqual(body["file_name"], "my_cv.pdf")
        resume = Resume.objects.get(candidate=self.cand2)
        self.assertEqual(resume.title, "My CV")
        self.assertEqual(len(self.stored_files()), 1)

    def test_candidate_uploads_docx(self):
        self.login(self.cand2)
        r = self.upload(docx())
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 1)

    def test_extension_check_is_case_insensitive(self):
        self.login(self.cand2)
        self.assertEqual(self.upload(pdf("CV.PDF")).status_code, 201)
        self.assertEqual(self.upload(docx("CV.DocX")).status_code, 201)

    def test_owner_comes_from_login_not_body(self):
        self.login(self.cand2)
        r = self.upload(pdf(), candidate=self.cand.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Resume.objects.get(candidate=self.cand2).title, "My CV")
        self.assertFalse(Resume.objects.filter(candidate=self.cand, title="My CV").exists())

    def test_employer_cannot_upload(self):
        self.login(self.emp1)
        r = self.upload(pdf())
        self.assert_error(r, 403, "permission_denied")
        self.assertEqual(Resume.objects.filter(title="My CV").count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_anonymous_cannot_upload(self):
        self.assert_error(self.upload(pdf()), 401, "not_authenticated")

    def test_wrong_extension_rejected(self):
        self.login(self.cand2)
        for name in ["cv.txt", "cv.exe", "cv.doc", "cv", "cv.pdf.exe"]:
            r = self.upload(pdf(name))
            self.assert_error(r, 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_fake_pdf_rejected_by_content(self):
        self.login(self.cand2)
        r = self.upload(pdf("cv.pdf", content=b"MZ\x90\x00\x03\x00\x00\x00 not a pdf"))
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_fake_docx_rejected_by_content(self):
        self.login(self.cand2)
        r = self.upload(docx("cv.docx", content=b"just some text"))
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)

    def test_content_must_match_extension(self):
        self.login(self.cand2)
        self.assert_error(self.upload(docx("cv.pdf")), 400, "validation_error")
        self.assert_error(self.upload(pdf("cv.docx")), 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)

    def test_empty_file_rejected(self):
        self.login(self.cand2)
        r = self.upload(pdf("cv.pdf", content=b""))
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)

    def test_file_over_2mb_rejected(self):
        self.login(self.cand2)
        too_big = b"%PDF-" + b"0" * (MAX_BYTES - 5 + 1)
        self.assertEqual(len(too_big), MAX_BYTES + 1)
        r = self.upload(pdf("cv.pdf", content=too_big))
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_file_of_exactly_2mb_accepted(self):
        self.login(self.cand2)
        exact = b"%PDF-" + b"0" * (MAX_BYTES - 5)
        self.assertEqual(len(exact), MAX_BYTES)
        r = self.upload(pdf("cv.pdf", content=exact))
        self.assertEqual(r.status_code, 201)

    def test_missing_file_rejected(self):
        self.login(self.cand2)
        self.assert_error(self.upload(None), 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)

    def test_file_sent_as_plain_text_rejected(self):
        self.login(self.cand2)
        r = self.client.post(RESUMES, {"title": "x", "file": "not a file"}, format="multipart")
        self.assert_error(r, 400, "validation_error")

    def test_missing_title_rejected(self):
        self.login(self.cand2)
        r = self.client.post(RESUMES, {"file": pdf()}, format="multipart")
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)
        self.assertEqual(self.stored_files(), [])

    def test_title_over_255_characters_rejected(self):
        self.login(self.cand2)
        r = self.upload(pdf(), title="x" * 256)
        self.assert_error(r, 400, "validation_error")
        self.assertEqual(Resume.objects.filter(candidate=self.cand2).count(), 0)
        self.assertEqual(self.stored_files(), [])


class ResumeListTests(Base):
    def test_candidate_sees_only_own_resumes(self):
        self.make_resume(self.cand, "Second")
        self.make_resume(self.cand2, "Not mine")
        self.login(self.cand)
        r = self.client.get(RESUMES)
        self.assert_list_shape(r)
        body = r.json()
        self.assertEqual(body["count"], 2)
        titles = {item["title"] for item in body["results"]}
        self.assertEqual(titles, {"CV", "Second"})
        for item in body["results"]:
            self.assertEqual(set(item.keys()), RESUME_FIELDS)

    def test_candidate_with_no_resumes_gets_empty_list(self):
        self.login(self.cand2)
        r = self.client.get(RESUMES)
        self.assert_list_shape(r)
        self.assertEqual(r.json()["results"], [])

    def test_employer_cannot_list_resumes(self):
        self.login(self.emp1)
        self.assert_error(self.client.get(RESUMES), 403, "permission_denied")

    def test_anonymous_cannot_list_resumes(self):
        self.assert_error(self.client.get(RESUMES), 401, "not_authenticated")

    def test_resume_list_page_out_of_range_is_404(self):
        self.login(self.cand)
        self.assert_error(self.client.get(RESUMES, {"page": 99}), 404, "not_found")


# ---------------------------------------------------------------- apply

class ApplyTests(Base):
    def test_candidate_applies(self):
        self.login(self.cand)
        r = self.apply()
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(set(body.keys()), APPLICATION_FIELDS)
        self.assertEqual(body["job"], self.job.id)
        self.assertEqual(body["resume"], self.resume.id)
        self.assertEqual(body["status"], "applied")
        self.assertEqual(body["job_title"], "Backend Engineer")
        self.assertEqual(body["company_name"], "Acme")
        self.assertEqual(body["candidate_username"], "cand")
        application = Application.objects.get()
        self.assertEqual(application.candidate, self.cand)
        self.assertEqual(application.status, "applied")

    def test_apply_creates_exactly_one_notification_for_the_job_owner(self):
        self.login(self.cand)
        self.apply()
        self.assertEqual(Notification.objects.count(), 1)
        note = Notification.objects.get()
        self.assertEqual(note.recipient, self.emp1)
        self.assertEqual(note.application, Application.objects.get())
        self.assertEqual(note.message, "cand applied for Backend Engineer")
        self.assertFalse(note.is_read)
        self.assertEqual(Notification.objects.filter(recipient=self.emp2).count(), 0)

    def test_employer_cannot_apply(self):
        self.login(self.emp2)
        self.assert_error(self.apply(), 403, "permission_denied")
        self.assert_no_application_or_notification()

    def test_anonymous_cannot_apply(self):
        self.assert_error(self.apply(), 401, "not_authenticated")
        self.assert_no_application_or_notification()

    def test_closed_job_refused(self):
        closed = self.make_job(title="Old job", is_open=False)
        self.login(self.cand)
        self.assert_error(self.apply(job=closed), 400, "job_closed")
        self.assert_no_application_or_notification()

    def test_duplicate_refused_and_creates_nothing_new(self):
        self.login(self.cand)
        self.assertEqual(self.apply().status_code, 201)
        r = self.apply()
        self.assert_error(r, 400, "duplicate_application")
        self.assertEqual(Application.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)

    def test_retry_after_success_is_safe(self):
        self.login(self.cand)
        first = self.apply()
        self.assertEqual(first.status_code, 201)
        for _ in range(2):
            self.assert_error(self.apply(), 400, "duplicate_application")
        self.assertEqual(Application.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Application.objects.get().id, first.json()["id"])

    def test_someone_elses_resume_refused(self):
        other_resume = self.make_resume(self.cand2, "Theirs")
        self.login(self.cand)
        self.assert_error(self.apply(resume=other_resume), 400, "invalid_resume")
        self.assert_no_application_or_notification()

    def test_two_candidates_can_apply_to_the_same_job(self):
        self.login(self.cand)
        self.assertEqual(self.apply().status_code, 201)
        self.login(self.cand2)
        r = self.apply(resume=self.make_resume(self.cand2))
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Application.objects.count(), 2)
        self.assertEqual(Notification.objects.count(), 2)

    def test_same_candidate_can_apply_to_two_jobs(self):
        other_job = self.make_job(title="Second job")
        self.login(self.cand)
        self.assertEqual(self.apply().status_code, 201)
        self.assertEqual(self.apply(job=other_job).status_code, 201)
        self.assertEqual(Application.objects.count(), 2)

    def test_bad_job_ids_rejected(self):
        self.login(self.cand)
        for bad in [999999, "abc", None, [1], {"a": 1}]:
            r = self.client.post(APPLICATIONS, {"job": bad, "resume": self.resume.id}, format="json")
            self.assert_error(r, 400, "validation_error")
        r = self.client.post(APPLICATIONS, {"resume": self.resume.id}, format="json")
        self.assert_error(r, 400, "validation_error")
        self.assert_no_application_or_notification()

    def test_bad_resume_ids_rejected(self):
        self.login(self.cand)
        for bad in [999999, "abc", None, [1], {"a": 1}]:
            r = self.client.post(APPLICATIONS, {"job": self.job.id, "resume": bad}, format="json")
            self.assert_error(r, 400, "validation_error")
        r = self.client.post(APPLICATIONS, {"job": self.job.id}, format="json")
        self.assert_error(r, 400, "validation_error")
        self.assert_no_application_or_notification()

    def test_empty_and_malformed_bodies_rejected(self):
        self.login(self.cand)
        self.assert_error(self.client.post(APPLICATIONS, {}, format="json"), 400, "validation_error")
        r = self.client.generic("POST", APPLICATIONS, "{bad json", content_type="application/json")
        self.assert_error(r, 400, "validation_error")
        self.assert_no_application_or_notification()

    def test_status_cannot_be_set_on_apply(self):
        self.login(self.cand)
        r = self.client.post(
            APPLICATIONS,
            {"job": self.job.id, "resume": self.resume.id, "status": "hired", "candidate": self.cand2.id},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        application = Application.objects.get()
        self.assertEqual(application.status, "applied")
        self.assertEqual(application.candidate, self.cand)

    # Check order from TASK_5: ids exist, then job open, then resume owner, then duplicate.
    def test_missing_resume_beats_closed_job(self):
        closed = self.make_job(is_open=False)
        self.login(self.cand)
        r = self.client.post(APPLICATIONS, {"job": closed.id, "resume": 999999}, format="json")
        self.assert_error(r, 400, "validation_error")

    def test_closed_job_beats_invalid_resume(self):
        closed = self.make_job(is_open=False)
        other_resume = self.make_resume(self.cand2)
        self.login(self.cand)
        self.assert_error(self.apply(job=closed, resume=other_resume), 400, "job_closed")

    def test_closed_job_beats_duplicate(self):
        self.make_app()
        self.job.is_open = False
        self.job.save()
        self.login(self.cand)
        self.assert_error(self.apply(), 400, "job_closed")

    def test_invalid_resume_beats_duplicate(self):
        self.make_app()
        other_resume = self.make_resume(self.cand2)
        self.login(self.cand)
        self.assert_error(self.apply(resume=other_resume), 400, "invalid_resume")
        self.assertEqual(Application.objects.count(), 1)

    def test_apply_is_atomic_when_notification_fails(self):
        self.login(self.cand)
        self.client.raise_request_exception = False
        with mock.patch.object(Notification, "save", side_effect=RuntimeError("boom")):
            r = self.apply()
        self.assert_error(r, 500, "server_error")
        self.assertNotIn("boom", r.content.decode())
        self.assert_no_application_or_notification()

    def test_unique_constraint_firing_returns_400_not_500(self):
        self.login(self.cand)
        self.assertEqual(self.apply().status_code, 201)
        real_exists = QuerySet.exists

        def exists_but_blind_to_applications(qs, *args, **kwargs):
            if qs.model is Application:
                return False
            return real_exists(qs, *args, **kwargs)

        with mock.patch.object(QuerySet, "exists", exists_but_blind_to_applications):
            r = self.apply()
        self.assert_error(r, 400, "duplicate_application")
        self.assertEqual(Application.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 1)


# ---------------------------------------------------------------- list and detail

class ApplicationListTests(Base):
    def test_candidate_sees_only_own_applications(self):
        mine = self.make_app(self.cand)
        self.make_app(self.cand2)
        self.login(self.cand)
        r = self.client.get(APPLICATIONS)
        self.assert_list_shape(r)
        body = r.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], mine.id)

    def test_employer_sees_only_applications_to_own_jobs(self):
        job2 = self.make_job(company=self.company2, title="Globex job")
        to_emp1 = self.make_app(self.cand, self.job)
        self.make_app(self.cand, job2)
        self.login(self.emp1)
        r = self.client.get(APPLICATIONS)
        self.assert_list_shape(r)
        body = r.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["id"], to_emp1.id)

    def test_employer_with_no_applications_gets_empty_list(self):
        self.login(self.emp2)
        r = self.client.get(APPLICATIONS)
        self.assert_list_shape(r)
        self.assertEqual(r.json()["results"], [])

    def test_anonymous_cannot_list(self):
        self.assert_error(self.client.get(APPLICATIONS), 401, "not_authenticated")

    def test_items_have_exactly_the_agreed_fields_and_no_emails(self):
        self.make_app()
        for user in (self.cand, self.emp1):
            self.login(user)
            r = self.client.get(APPLICATIONS)
            item = r.json()["results"][0]
            self.assertEqual(set(item.keys()), APPLICATION_FIELDS)
            self.assertNotIn("example.com", r.content.decode())

    def test_newest_first_for_both_roles(self):
        ids = []
        for i in range(3):
            job = self.make_job(title=f"Job {i}")
            ids.append(self.make_app(self.cand, job).id)
        expected = sorted(ids, reverse=True)
        for user in (self.cand, self.emp1):
            self.login(user)
            got = [item["id"] for item in self.client.get(APPLICATIONS).json()["results"]]
            self.assertEqual(got, expected)

    def test_pagination_10_per_page(self):
        for i in range(11):
            self.make_app(self.cand, self.make_job(title=f"Job {i}"))
        self.login(self.cand)
        page1 = self.client.get(APPLICATIONS).json()
        self.assertEqual(page1["count"], 11)
        self.assertEqual(len(page1["results"]), 10)
        self.assertIsNotNone(page1["next"])
        self.assertIsNone(page1["previous"])
        page2 = self.client.get(APPLICATIONS, {"page": 2}).json()
        self.assertEqual(len(page2["results"]), 1)
        self.assertIsNone(page2["next"])

    def test_page_out_of_range_is_404(self):
        self.login(self.cand)
        self.assert_error(self.client.get(APPLICATIONS, {"page": 99}), 404, "not_found")


class ApplicationDetailTests(Base):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.url = f"{APPLICATIONS}{self.app.id}/"

    def test_candidate_who_applied_can_read(self):
        self.login(self.cand)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.json().keys()), APPLICATION_FIELDS)
        self.assertEqual(r.json()["id"], self.app.id)
        self.assertNotIn("example.com", r.content.decode())

    def test_owning_employer_can_read(self):
        self.login(self.emp1)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["candidate_username"], "cand")
        self.assertNotIn("example.com", r.content.decode())

    def test_other_candidate_gets_404(self):
        self.login(self.cand2)
        self.assert_error(self.client.get(self.url), 404, "not_found")

    def test_other_employer_gets_404(self):
        self.login(self.emp2)
        self.assert_error(self.client.get(self.url), 404, "not_found")

    def test_anonymous_gets_401(self):
        self.assert_error(self.client.get(self.url), 401, "not_authenticated")

    def test_unknown_id_is_404(self):
        self.login(self.cand)
        self.assert_error(self.client.get(f"{APPLICATIONS}999999/"), 404, "not_found")


# ---------------------------------------------------------------- status

class StatusTests(Base):
    def status_url(self, application):
        return f"{APPLICATIONS}{application.id}/status/"

    def patch_status(self, application, value):
        return self.client.patch(self.status_url(application), {"status": value}, format="json")

    def test_every_allowed_move_works(self):
        self.login(self.emp1)
        for start, targets in ALLOWED_MOVES.items():
            for target in targets:
                with self.subTest(start=start, target=target):
                    app = self.make_app(job=self.make_job(title=f"{start}-{target}"), status=start)
                    r = self.patch_status(app, target)
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(set(r.json().keys()), APPLICATION_FIELDS)
                    self.assertEqual(r.json()["status"], target)
                    app.refresh_from_db()
                    self.assertEqual(app.status, target)

    def test_every_other_move_is_invalid_transition(self):
        self.login(self.emp1)
        for start in ALL_STATUSES:
            for target in ALL_STATUSES:
                if target in ALLOWED_MOVES[start]:
                    continue
                with self.subTest(start=start, target=target):
                    app = self.make_app(job=self.make_job(title=f"{start}-{target}"), status=start)
                    before = Application.objects.get(pk=app.pk)
                    r = self.patch_status(app, target)
                    self.assert_error(r, 400, "invalid_transition")
                    after = Application.objects.get(pk=app.pk)
                    self.assertEqual(after.status, start)
                    self.assertEqual(after.updated_at, before.updated_at)

    def test_same_status_is_invalid_transition(self):
        self.login(self.emp1)
        app = self.make_app(status="reviewing")
        self.assert_error(self.patch_status(app, "reviewing"), 400, "invalid_transition")
        app.refresh_from_db()
        self.assertEqual(app.status, "reviewing")

    def test_unknown_or_bad_status_value_is_validation_error(self):
        self.login(self.emp1)
        app = self.make_app()
        for bad in ["banana", "", None, 5, ["hired"], "HIRED"]:
            with self.subTest(bad=bad):
                self.assert_error(self.patch_status(app, bad), 400, "validation_error")
        r = self.client.patch(self.status_url(app), {}, format="json")
        self.assert_error(r, 400, "validation_error")
        r = self.client.generic("PATCH", self.status_url(app), "{bad json", content_type="application/json")
        self.assert_error(r, 400, "validation_error")
        app.refresh_from_db()
        self.assertEqual(app.status, "applied")

    def test_candidate_gets_403_even_on_own_application(self):
        self.login(self.cand)
        app = self.make_app()
        self.assert_error(self.patch_status(app, "reviewing"), 403, "permission_denied")
        app.refresh_from_db()
        self.assertEqual(app.status, "applied")

    def test_other_employer_gets_404(self):
        self.login(self.emp2)
        app = self.make_app()
        self.assert_error(self.patch_status(app, "reviewing"), 404, "not_found")
        app.refresh_from_db()
        self.assertEqual(app.status, "applied")

    def test_anonymous_gets_401(self):
        app = self.make_app()
        self.assert_error(self.patch_status(app, "reviewing"), 401, "not_authenticated")

    def test_unknown_application_is_404(self):
        self.login(self.emp1)
        r = self.client.patch(f"{APPLICATIONS}999999/status/", {"status": "reviewing"}, format="json")
        self.assert_error(r, 404, "not_found")

    def test_get_on_status_url_is_405(self):
        self.login(self.emp1)
        app = self.make_app()
        self.assert_error(self.client.get(self.status_url(app)), 405, "method_not_allowed")

    def test_updated_at_changes_on_success(self):
        self.login(self.emp1)
        app = self.make_app()
        # auto_now can give the same clock reading twice, so move the old value into the past.
        # .update() skips auto_now, so the PATCH is guaranteed a later value.
        before = timezone.now() - timedelta(minutes=1)
        Application.objects.filter(pk=app.pk).update(updated_at=before)
        self.assertEqual(self.patch_status(app, "reviewing").status_code, 200)
        app.refresh_from_db()
        self.assertGreater(app.updated_at, before)

    def test_only_status_changes(self):
        self.login(self.emp1)
        app = self.make_app()
        other_job = self.make_job(title="Other")
        other_resume = self.make_resume(self.cand2)
        r = self.client.patch(
            self.status_url(app),
            {
                "status": "reviewing",
                "job": other_job.id,
                "resume": other_resume.id,
                "candidate": self.cand2.id,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.status, "reviewing")
        self.assertEqual(app.job, self.job)
        self.assertEqual(app.resume, self.resume)
        self.assertEqual(app.candidate, self.cand)

    def test_status_change_creates_no_notification(self):
        self.login(self.emp1)
        app = self.make_app()
        self.patch_status(app, "reviewing")
        self.assertEqual(Notification.objects.count(), 0)


# ---------------------------------------------------------------- notifications

class NotificationTests(Base):
    def make_note(self, recipient, application, message="msg"):
        return Notification.objects.create(recipient=recipient, application=application, message=message)

    def test_employer_sees_only_own_notifications(self):
        app1 = self.make_app()
        job2 = self.make_job(company=self.company2, title="Globex job")
        app2 = self.make_app(self.cand, job2)
        mine = self.make_note(self.emp1, app1, "for emp1")
        self.make_note(self.emp2, app2, "for emp2")
        self.login(self.emp1)
        r = self.client.get(NOTIFICATIONS)
        self.assert_list_shape(r)
        body = r.json()
        self.assertEqual(body["count"], 1)
        item = body["results"][0]
        self.assertEqual(set(item.keys()), NOTIFICATION_FIELDS)
        self.assertEqual(item["id"], mine.id)
        self.assertEqual(item["application"], app1.id)
        self.assertEqual(item["message"], "for emp1")
        self.assertFalse(item["is_read"])

    def test_newest_first(self):
        app = self.make_app()
        ids = [self.make_note(self.emp1, app, f"n{i}").id for i in range(3)]
        self.login(self.emp1)
        got = [item["id"] for item in self.client.get(NOTIFICATIONS).json()["results"]]
        self.assertEqual(got, sorted(ids, reverse=True))

    def test_pagination_10_per_page(self):
        app = self.make_app()
        for i in range(11):
            self.make_note(self.emp1, app, f"n{i}")
        self.login(self.emp1)
        page1 = self.client.get(NOTIFICATIONS).json()
        self.assertEqual(page1["count"], 11)
        self.assertEqual(len(page1["results"]), 10)
        self.assertEqual(len(self.client.get(NOTIFICATIONS, {"page": 2}).json()["results"]), 1)
        self.assert_error(self.client.get(NOTIFICATIONS, {"page": 99}), 404, "not_found")

    def test_employer_with_none_gets_empty_list(self):
        self.login(self.emp2)
        r = self.client.get(NOTIFICATIONS)
        self.assert_list_shape(r)
        self.assertEqual(r.json()["results"], [])

    def test_candidate_gets_403(self):
        self.login(self.cand)
        self.assert_error(self.client.get(NOTIFICATIONS), 403, "permission_denied")

    def test_anonymous_gets_401(self):
        self.assert_error(self.client.get(NOTIFICATIONS), 401, "not_authenticated")

    def test_apply_then_employer_sees_the_notification(self):
        self.login(self.cand)
        self.apply()
        self.login(self.emp1)
        body = self.client.get(NOTIFICATIONS).json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["results"][0]["message"], "cand applied for Backend Engineer")


# ---------------------------------------------------------------- closed job later

class ClosedJobLaterTests(Base):
    def setUp(self):
        super().setUp()
        self.app = self.make_app()
        self.job.is_open = False
        self.job.save()

    def test_existing_application_stays_visible_to_both_sides(self):
        for user in (self.cand, self.emp1):
            self.login(user)
            listing = self.client.get(APPLICATIONS).json()
            self.assertEqual(listing["count"], 1)
            detail = self.client.get(f"{APPLICATIONS}{self.app.id}/")
            self.assertEqual(detail.status_code, 200)

    def test_employer_can_still_change_status(self):
        self.login(self.emp1)
        r = self.client.patch(f"{APPLICATIONS}{self.app.id}/status/", {"status": "reviewing"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status, "reviewing")

    def test_new_applications_are_refused(self):
        self.login(self.cand2)
        r = self.apply(resume=self.make_resume(self.cand2))
        self.assert_error(r, 400, "job_closed")
        self.assertEqual(Application.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 0)