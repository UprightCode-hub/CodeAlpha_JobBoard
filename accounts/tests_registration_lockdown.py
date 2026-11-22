"""Public registration lockdown: signups are always candidates.

Drop into accounts/. Run: python manage.py test accounts.tests_registration_lockdown

Contract assumed (from the repo): ``role`` is a read-only serializer field, so a
submitted role is IGNORED (201, role == "candidate"), not rejected. If you later
change this to reject with 400, update test_submitted_role_is_ignored.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

User = get_user_model()

PASSWORD = "Str0ng-Passw0rd!x9"
USER_KEYS = {"id", "username", "email", "role"}


def payload(**overrides):
    data = {"username": "newuser", "email": "newuser@example.com", "password": PASSWORD}
    data.update(overrides)
    return data


class RegistrationBase(APITestCase):
    def setUp(self):
        self.register_url = reverse("register")
        self.login_url = reverse("login")
        self.me_url = reverse("me")

    def register(self, **overrides):
        return self.client.post(self.register_url, payload(**overrides), format="json")

    def token_for(self, username="newuser"):
        r = self.client.post(
            self.login_url, {"username": username, "password": PASSWORD}, format="json"
        )
        self.assertEqual(r.status_code, 200, r.content[:300])
        return r.json()["access"]

    def authenticate(self, token):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)


class PublicSignupTests(RegistrationBase):
    def test_plain_registration_creates_a_candidate(self):
        r = self.register()
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(r.json()["role"], "candidate")
        self.assertEqual(User.objects.get(username="newuser").role, "candidate")

    def test_submitted_role_is_ignored(self):
        for value in (
            "employer",
            "EMPLOYER",
            " employer ",
            "admin",
            "superuser",
            "",
            None,
            1,
            True,
            ["employer"],
            {"role": "employer"},
        ):
            with self.subTest(role=value):
                User.objects.all().delete()
                r = self.register(role=value)
                self.assertEqual(r.status_code, 201, r.content[:300])
                self.assertEqual(r.json()["role"], "candidate")
                self.assertEqual(User.objects.get().role, "candidate")

    def test_missing_role_is_fine(self):
        r = self.client.post(self.register_url, payload(), format="json")
        self.assertEqual(r.status_code, 201)

    def test_form_encoded_role_is_also_ignored(self):
        r = self.client.post(self.register_url, payload(role="employer"))
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(User.objects.get().role, "candidate")

    def test_privilege_fields_in_body_are_ignored(self):
        r = self.register(
            is_staff=True,
            is_superuser=True,
            is_active=False,
            id=99999,
            groups=[1],
            user_permissions=[1],
        )
        self.assertEqual(r.status_code, 201, r.content[:300])
        user = User.objects.get()
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertNotEqual(user.pk, 99999)
        self.assertEqual(user.groups.count(), 0)
        self.assertEqual(user.user_permissions.count(), 0)

    def test_response_exposes_only_public_fields(self):
        body = self.register().json()
        self.assertEqual(set(body), USER_KEYS)
        self.assertNotIn(PASSWORD, str(body))

    def test_password_is_hashed(self):
        self.register()
        user = User.objects.get()
        self.assertNotEqual(user.password, PASSWORD)
        self.assertTrue(user.check_password(PASSWORD))

    def test_duplicate_username_and_email_rejected(self):
        self.assertEqual(self.register().status_code, 201)
        for overrides in ({"email": "other@example.com"}, {"username": "other"}):
            with self.subTest(overrides):
                r = self.register(**overrides)
                self.assertEqual(r.status_code, 400)
                self.assertEqual(r.json()["error"]["code"], "validation_error")
        self.assertEqual(User.objects.count(), 1)

    def test_failed_registration_creates_no_user(self):
        data = payload(role="employer")
        del data["password"]
        r = self.client.post(self.register_url, data, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "validation_error")
        self.assertEqual(User.objects.count(), 0)

    def test_malformed_bodies_give_400_not_500(self):
        for body in ("{not json", "[]", '"a string"', "null", ""):
            with self.subTest(body=body):
                r = self.client.post(
                    self.register_url, body, content_type="application/json"
                )
                self.assertEqual(r.status_code, 400, r.content[:300])
                self.assertEqual(r.json()["error"]["code"], "validation_error")
        self.assertEqual(User.objects.count(), 0)

    def test_serializer_declares_role_read_only(self):
        from accounts.serializers import RegisterSerializer

        self.assertTrue(RegisterSerializer().fields["role"].read_only)


class NoSelfServiceEscalationTests(RegistrationBase):
    def setUp(self):
        super().setUp()
        self.register()
        self.authenticate(self.token_for())
        self.user = User.objects.get(username="newuser")

    def test_me_reports_candidate_even_after_asking_for_employer(self):
        User.objects.all().delete()
        self.client.credentials()
        self.register(role="employer")
        self.authenticate(self.token_for())
        r = self.client.get(self.me_url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["role"], "candidate")

    def test_me_cannot_be_used_to_change_role(self):
        for method in ("patch", "put", "post", "delete"):
            with self.subTest(method=method):
                r = getattr(self.client, method)(
                    self.me_url, {"role": "employer"}, format="json"
                )
                self.assertEqual(r.status_code, 405, r.content[:300])
                self.assertEqual(r.json()["error"]["code"], "method_not_allowed")
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, "candidate")

    def test_fresh_signup_is_blocked_from_every_employer_endpoint(self):
        company = {"name": "Evil Corp", "description": "d"}
        checks = [
            ("post", reverse("company"), company),
            ("get", reverse("company"), None),
            ("get", reverse("notifications"), None),
            (
                "post",
                reverse("job-create"),
                {
                    "title": "t",
                    "description": "d",
                    "location": "Lagos",
                    "job_type": "full_time",
                    "work_model": "remote",
                    "experience_level": "mid",
                    "min_years_experience": 1,
                },
            ),
        ]
        for method, url, data in checks:
            with self.subTest(method=method, url=url):
                r = getattr(self.client, method)(url, data, format="json")
                self.assertEqual(r.status_code, 403, r.content[:300])
                self.assertEqual(r.json()["error"]["code"], "permission_denied")

    def test_candidate_can_use_candidate_endpoints(self):
        self.assertEqual(self.client.get(reverse("resumes")).status_code, 200)
        self.assertEqual(self.client.get(reverse("applications")).status_code, 200)


class AdminOnlyPromotionTests(RegistrationBase):
    """Employer status comes only from a trusted write to the user row (admin)."""

    def test_promotion_by_admin_takes_effect_on_the_existing_token(self):
        self.register()
        self.authenticate(self.token_for())
        company = {"name": "Acme", "description": "d"}

        before = self.client.post(reverse("company"), company, format="json")
        self.assertEqual(before.status_code, 403)

        User.objects.filter(username="newuser").update(role="employer")  # admin action

        after = self.client.post(reverse("company"), company, format="json")
        self.assertEqual(after.status_code, 201, after.content[:300])
        self.assertEqual(self.client.get(self.me_url).json()["role"], "employer")

    def test_demotion_takes_effect_immediately(self):
        self.register()
        User.objects.filter(username="newuser").update(role="employer")
        self.authenticate(self.token_for())
        self.assertEqual(
            self.client.post(
                reverse("company"), {"name": "A", "description": "d"}, format="json"
            ).status_code,
            201,
        )
        User.objects.filter(username="newuser").update(role="candidate")
        self.assertEqual(self.client.get(reverse("company")).status_code, 403)

    def test_superuser_can_open_user_admin_and_sees_the_role_field(self):
        self.register()
        boss = User.objects.create(
            username="boss",
            email="boss@example.com",
            role="employer",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(boss)
        target = User.objects.get(username="newuser")
        r = self.client.get(reverse("admin:accounts_user_change", args=[target.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn('name="role"', r.content.decode())

    def test_non_staff_users_cannot_reach_the_admin(self):
        self.register()
        self.client.force_login(User.objects.get(username="newuser"))
        r = self.client.get(reverse("admin:index"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r["Location"])
        r = self.client.get(
            reverse("admin:accounts_user_change", args=[User.objects.get().pk])
        )
        self.assertEqual(r.status_code, 302)
