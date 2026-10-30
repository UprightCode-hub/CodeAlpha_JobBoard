"""Tests for account registration, authentication, and current-user APIs."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

REGISTER = "/api/auth/register/"
LOGIN = "/api/auth/login/"
ME = "/api/auth/me/"

User = get_user_model()


def good_payload(**overrides):
    data = {
        "username": "ada",
        "email": "ada@example.com",
        "password": "StrongPass123!",
        "role": "candidate",
    }
    data.update(overrides)
    return data


class ErrorShapeMixin:
    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertIn("error", body)
        self.assertEqual(body["error"]["code"], code)
        self.assertIsInstance(body["error"]["message"], str)
        self.assertTrue(body["error"]["message"].strip())


class UserModelTests(APITestCase):
    def test_custom_user_model_is_in_accounts_app(self):
        self.assertEqual(User._meta.label, "accounts.User")

    def test_user_has_role_field(self):
        self.assertTrue(hasattr(User, "role"))


class RegisterTests(ErrorShapeMixin, APITestCase):
    def test_register_candidate_returns_201_and_fields(self):
        r = self.client.post(REGISTER, good_payload(), format="json")
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["username"], "ada")
        self.assertEqual(body["email"], "ada@example.com")
        self.assertEqual(body["role"], "candidate")
        self.assertIn("id", body)

    def test_register_employer_works(self):
        r = self.client.post(REGISTER, good_payload(role="employer"), format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["role"], "employer")

    def test_password_is_never_returned(self):
        r = self.client.post(REGISTER, good_payload(), format="json")
        self.assertNotIn("password", r.json())

    def test_password_is_stored_hashed(self):
        self.client.post(REGISTER, good_payload(), format="json")
        user = User.objects.get(username="ada")
        self.assertNotEqual(user.password, "StrongPass123!")
        self.assertTrue(user.check_password("StrongPass123!"))

    def test_duplicate_username_rejected(self):
        self.client.post(REGISTER, good_payload(), format="json")
        r = self.client.post(
            REGISTER, good_payload(email="other@example.com"), format="json"
        )
        self.assert_error(r, 400, "validation_error")

    def test_duplicate_email_rejected(self):
        self.client.post(REGISTER, good_payload(), format="json")
        r = self.client.post(
            REGISTER, good_payload(username="grace"), format="json"
        )
        self.assert_error(r, 400, "validation_error")

    def test_invalid_role_rejected(self):
        r = self.client.post(REGISTER, good_payload(role="admin"), format="json")
        self.assert_error(r, 400, "validation_error")

    def test_missing_role_rejected(self):
        payload = good_payload()
        del payload["role"]
        r = self.client.post(REGISTER, payload, format="json")
        self.assert_error(r, 400, "validation_error")

    def test_missing_email_rejected(self):
        payload = good_payload()
        del payload["email"]
        r = self.client.post(REGISTER, payload, format="json")
        self.assert_error(r, 400, "validation_error")


class LoginTests(ErrorShapeMixin, APITestCase):
    def setUp(self):
        self.client.post(REGISTER, good_payload(), format="json")

    def test_login_returns_access_and_refresh(self):
        r = self.client.post(
            LOGIN, {"username": "ada", "password": "StrongPass123!"}, format="json"
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("access", body)
        self.assertIn("refresh", body)

    def test_wrong_password_gives_401_not_authenticated(self):
        r = self.client.post(
            LOGIN, {"username": "ada", "password": "wrong"}, format="json"
        )
        self.assert_error(r, 401, "not_authenticated")

    def test_unknown_user_gives_401_not_authenticated(self):
        r = self.client.post(
            LOGIN, {"username": "nobody", "password": "x"}, format="json"
        )
        self.assert_error(r, 401, "not_authenticated")


class MeTests(ErrorShapeMixin, APITestCase):
    def test_me_without_token_gives_401_not_authenticated(self):
        r = self.client.get(ME)
        self.assert_error(r, 401, "not_authenticated")

    def test_me_with_garbage_token_gives_401_not_authenticated(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer notatoken")
        r = self.client.get(ME)
        self.assert_error(r, 401, "not_authenticated")

    def test_me_with_token_returns_own_data(self):
        self.client.post(REGISTER, good_payload(role="employer"), format="json")
        login = self.client.post(
            LOGIN, {"username": "ada", "password": "StrongPass123!"}, format="json"
        )
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + login.json()["access"])
        r = self.client.get(ME)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["username"], "ada")
        self.assertEqual(body["email"], "ada@example.com")
        self.assertEqual(body["role"], "employer")
        self.assertNotIn("password", body)


class TokenFailureTests(ErrorShapeMixin, APITestCase):
    def setUp(self):
        self.client.post(REGISTER, good_payload(), format="json")
        self.user = User.objects.get(username="ada")

    def get_me_with(self, token):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        return self.client.get(ME)

    def test_expired_token_rejected(self):
        token = AccessToken.for_user(self.user)
        token.set_exp(lifetime=-timedelta(seconds=5))
        self.assert_error(self.get_me_with(str(token)), 401, "not_authenticated")

    def test_tampered_token_rejected(self):
        token = str(AccessToken.for_user(self.user))
        tampered = token[:-3] + ("abc" if not token.endswith("abc") else "xyz")
        self.assert_error(self.get_me_with(tampered), 401, "not_authenticated")

    def test_refresh_token_cannot_be_used_as_access_token(self):
        token = str(RefreshToken.for_user(self.user))
        self.assert_error(self.get_me_with(token), 401, "not_authenticated")

    def test_token_of_deleted_user_rejected(self):
        token = str(AccessToken.for_user(self.user))
        self.user.delete()
        self.assert_error(self.get_me_with(token), 401, "not_authenticated")

    def test_token_of_inactive_user_rejected(self):
        token = str(AccessToken.for_user(self.user))
        self.user.is_active = False
        self.user.save()
        self.assert_error(self.get_me_with(token), 401, "not_authenticated")


class MalformedInputTests(ErrorShapeMixin, APITestCase):
    def test_malformed_json_on_register(self):
        r = self.client.post(REGISTER, "{not json", content_type="application/json")
        self.assert_error(r, 400, "validation_error")

    def test_empty_body_on_register(self):
        r = self.client.post(REGISTER, {}, format="json")
        self.assert_error(r, 400, "validation_error")

    def test_wrong_types_on_register(self):
        r = self.client.post(
            REGISTER, good_payload(username=["a", "b"]), format="json"
        )
        self.assert_error(r, 400, "validation_error")

    def test_login_with_missing_fields(self):
        r = self.client.post(LOGIN, {}, format="json")
        self.assert_error(r, 400, "validation_error")

    def test_failed_register_creates_no_user(self):
        self.client.post(REGISTER, good_payload(role="admin"), format="json")
        self.assertEqual(User.objects.count(), 0)

    def test_registering_twice_leaves_exactly_one_user(self):
        self.client.post(REGISTER, good_payload(), format="json")
        self.client.post(REGISTER, good_payload(), format="json")
        self.assertEqual(User.objects.count(), 1)


class GracefulErrorTests(ErrorShapeMixin, APITestCase):
    def test_unknown_url_returns_json_not_found(self):
        r = self.client.get("/api/this-does-not-exist/")
        self.assert_error(r, 404, "not_found")
        self.assertIn("application/json", r["Content-Type"])
