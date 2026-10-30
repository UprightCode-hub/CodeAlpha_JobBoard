"""Tests for application, resume, and notification models and database constraints."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, UniqueConstraint
from django.test import TestCase

from applications.models import Application, Notification, Resume
from jobs.models import Company, Job

User = get_user_model()


def make_user(username, role):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="StrongPass123!",
        role=role,
    )


class ModelBase(TestCase):
    def setUp(self):
        self.emp = make_user("emp", "employer")
        self.cand1 = make_user("cand1", "candidate")
        self.cand2 = make_user("cand2", "candidate")
        self.company = Company.objects.create(owner=self.emp, name="Acme", description="d")
        self.job1 = self.make_job("Backend Engineer")
        self.job2 = self.make_job("Data Analyst")
        self.resume1 = Resume.objects.create(
            candidate=self.cand1, title="CV", file="resumes/cv1.pdf"
        )
        self.resume2 = Resume.objects.create(
            candidate=self.cand2, title="CV", file="resumes/cv2.pdf"
        )

    def make_job(self, title):
        return Job.objects.create(
            company=self.company, title=title, description="d", location="Lagos",
            job_type="full_time", work_model="remote", experience_level="mid",
            min_years_experience=1,
        )

    def apply(self, candidate, job, resume):
        return Application.objects.create(candidate=candidate, job=job, resume=resume)


class ResumeTests(ModelBase):
    def test_resume_saves_fields_and_timestamp(self):
        self.assertEqual(self.resume1.candidate, self.cand1)
        self.assertEqual(self.resume1.title, "CV")
        self.assertEqual(self.resume1.file.name, "resumes/cv1.pdf")
        self.assertIsNotNone(self.resume1.uploaded_at)

    def test_candidate_can_have_many_resumes(self):
        Resume.objects.create(candidate=self.cand1, title="CV 2", file="resumes/cv1b.pdf")
        self.assertEqual(Resume.objects.filter(candidate=self.cand1).count(), 2)

    def test_deleting_candidate_without_applications_deletes_resumes(self):
        self.cand2.delete()
        self.assertFalse(Resume.objects.filter(title="CV", candidate_id=self.cand2.pk).exists())
        self.assertEqual(Resume.objects.count(), 1)


class ApplicationTests(ModelBase):
    def test_defaults(self):
        app = self.apply(self.cand1, self.job1, self.resume1)
        self.assertEqual(app.status, "applied")
        self.assertIsNotNone(app.applied_at)
        self.assertIsNotNone(app.updated_at)

    def test_status_choices_are_exactly_the_agreed_values(self):
        values = {value for value, _label in Application._meta.get_field("status").choices}
        self.assertEqual(values, {"applied", "reviewing", "shortlisted", "rejected", "hired"})

    def test_updated_at_moves_and_applied_at_stays(self):
        app = self.apply(self.cand1, self.job1, self.resume1)
        applied_at, updated_before = app.applied_at, app.updated_at
        app.status = "reviewing"
        app.save()
        app.refresh_from_db()
        self.assertEqual(app.applied_at, applied_at)
        self.assertGreaterEqual(app.updated_at, updated_before)

    def test_duplicate_application_is_blocked_by_the_database(self):
        self.apply(self.cand1, self.job1, self.resume1)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.apply(self.cand1, self.job1, self.resume1)
        self.assertEqual(Application.objects.count(), 1)

    def test_unique_constraint_is_declared_with_the_agreed_name(self):
        found = [
            c for c in Application._meta.constraints
            if isinstance(c, UniqueConstraint)
            and set(c.fields) == {"candidate", "job"}
        ]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].name, "unique_application_per_candidate_job")

    def test_same_candidate_can_apply_to_different_jobs(self):
        self.apply(self.cand1, self.job1, self.resume1)
        self.apply(self.cand1, self.job2, self.resume1)
        self.assertEqual(Application.objects.count(), 2)

    def test_different_candidates_can_apply_to_same_job(self):
        self.apply(self.cand1, self.job1, self.resume1)
        self.apply(self.cand2, self.job1, self.resume2)
        self.assertEqual(Application.objects.count(), 2)

    def test_job_with_applications_cannot_be_deleted(self):
        self.apply(self.cand1, self.job1, self.resume1)
        with self.assertRaises(ProtectedError):
            self.job1.delete()
        self.assertTrue(Job.objects.filter(pk=self.job1.pk).exists())

    def test_resume_used_in_an_application_cannot_be_deleted(self):
        self.apply(self.cand1, self.job1, self.resume1)
        with self.assertRaises(ProtectedError):
            self.resume1.delete()
        self.assertTrue(Resume.objects.filter(pk=self.resume1.pk).exists())

    def test_candidate_with_applications_cannot_be_deleted(self):
        self.apply(self.cand1, self.job1, self.resume1)
        with self.assertRaises(ProtectedError):
            self.cand1.delete()
        self.assertTrue(User.objects.filter(pk=self.cand1.pk).exists())


class NotificationTests(ModelBase):
    def test_defaults(self):
        app = self.apply(self.cand1, self.job1, self.resume1)
        n = Notification.objects.create(
            recipient=self.emp, application=app, message="New application"
        )
        self.assertFalse(n.is_read)
        self.assertIsNotNone(n.created_at)
        self.assertEqual(n.recipient, self.emp)
        self.assertEqual(n.application, app)

    def test_deleting_an_application_removes_its_notifications(self):
        app = self.apply(self.cand1, self.job1, self.resume1)
        Notification.objects.create(recipient=self.emp, application=app, message="New")
        app.delete()
        self.assertEqual(Notification.objects.count(), 0)
