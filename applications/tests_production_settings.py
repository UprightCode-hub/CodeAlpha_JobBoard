"""Production settings: fail-fast validation and HTTPS/cookie defaults.

Drop into applications/. Run:
python manage.py test applications.tests_production_settings

config/settings.py validates at import time, so each case imports it in a fresh
subprocess with a controlled environment (python-dotenv is stubbed out so your
local .env cannot change the result). No database connection is made.

KnownWeakKeyGaps documents two weaknesses in the current SECRET_KEY check; those
two tests are expected to FAIL until the check is tightened.
"""

import json
import os
import secrets
import subprocess
import sys
import textwrap

from django.conf import settings
from django.test import SimpleTestCase

ROOT = str(settings.BASE_DIR)

MANAGED = {
    "SECRET_KEY",
    "DEBUG",
    "ALLOWED_HOSTS",
    "DATABASE_URL",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_PORT",
    "SECURE_SSL_REDIRECT",
    "SESSION_COOKIE_SECURE",
    "CSRF_COOKIE_SECURE",
    "SECURE_HSTS_SECONDS",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    "SECURE_HSTS_PRELOAD",
    "DJANGO_SETTINGS_MODULE",
}

DB_DEFAULTS = {
    "DB_NAME": "jobboard_probe",
    "DB_USER": "probe",
    "DB_PASSWORD": "probe",
    "DB_HOST": "localhost",
    "DB_PORT": "5432",
}

PROBE = textwrap.dedent(
    """
    import dotenv, json
    dotenv.load_dotenv = lambda *a, **k: False
    import config.settings as s
    keys = ["SECRET_KEY", "DEBUG", "ALLOWED_HOSTS", "SECURE_SSL_REDIRECT",
            "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "SECURE_HSTS_SECONDS",
            "SECURE_HSTS_INCLUDE_SUBDOMAINS", "SECURE_HSTS_PRELOAD"]
    out = {k: getattr(s, k, None) for k in keys}
    db = s.DATABASES["default"]
    out["DB"] = {k: str(db.get(k)) for k in ("ENGINE", "NAME", "USER", "HOST", "PORT")}
    print("PROBE:" + json.dumps(out, default=str))
    """
)

DEPLOY_CHECK = textwrap.dedent(
    """
    import dotenv, os
    dotenv.load_dotenv = lambda *a, **k: False
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    from django.core.management import execute_from_command_line
    execute_from_command_line(["manage.py", "check", "--deploy"])
    """
)


def strong_key():
    return secrets.token_urlsafe(64)


def run(code, **env):
    full = {k: v for k, v in os.environ.items() if k not in MANAGED}
    full.update(DB_DEFAULTS)
    full.update({k: v for k, v in env.items() if v is not None})
    for k, v in env.items():
        if v is None:
            full.pop(k, None)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=full,
        capture_output=True,
        text=True,
        timeout=120,
    )


class ProbeMixin:
    def load(self, **env):
        result = run(PROBE, **env)
        self.assertEqual(
            result.returncode, 0, f"settings failed to import:\n{result.stderr[-1500:]}"
        )
        line = next(
            line for line in result.stdout.splitlines() if line.startswith("PROBE:")
        )
        return json.loads(line[len("PROBE:") :])

    def assert_refused(self, expect_in_message, **env):
        result = run(PROBE, **env)
        self.assertNotEqual(
            result.returncode, 0, "settings imported but should have been refused"
        )
        self.assertIn("ImproperlyConfigured", result.stderr)
        self.assertIn(expect_in_message, result.stderr)


class FailFastTests(ProbeMixin, SimpleTestCase):
    def test_weak_secret_keys_refused_when_debug_is_off(self):
        for label, key in (
            ("empty", ""),
            ("short", "abc123"),
            ("changeme", "changeme"),
            ("secret", "secret"),
            ("49 chars", secrets.token_urlsafe(40)[:49]),
        ):
            with self.subTest(label):
                self.assert_refused(
                    "SECRET_KEY",
                    DEBUG="False",
                    SECRET_KEY=key,
                    ALLOWED_HOSTS="api.example.com",
                )

    def test_missing_secret_key_refused(self):
        self.assert_refused(
            "SECRET_KEY",
            DEBUG="False",
            SECRET_KEY=None,
            ALLOWED_HOSTS="api.example.com",
        )

    def test_exactly_50_char_random_key_accepted(self):
        out = self.load(
            DEBUG="False",
            SECRET_KEY=secrets.token_urlsafe(40)[:50],
            ALLOWED_HOSTS="api.example.com",
        )
        self.assertEqual(len(out["SECRET_KEY"]), 50)

    def test_empty_allowed_hosts_refused_when_debug_is_off(self):
        for label, hosts in (
            ("empty", ""),
            ("spaces", "   "),
            ("commas", ",, ,"),
            ("unset", None),
        ):
            with self.subTest(label):
                self.assert_refused(
                    "ALLOWED_HOSTS",
                    DEBUG="False",
                    SECRET_KEY=strong_key(),
                    ALLOWED_HOSTS=hosts,
                )

    def test_debug_defaults_to_off_so_a_missing_variable_fails_closed(self):
        self.assert_refused(
            "SECRET_KEY", DEBUG=None, SECRET_KEY="weak", ALLOWED_HOSTS="api.example.com"
        )

    def test_unrecognised_debug_values_count_as_off(self):
        for value in (
            "",
            "0",
            "no",
            "off",
            "false",
            "False",
            "enabled",
            "yes please",
            "tru",
        ):
            with self.subTest(value=value):
                self.assert_refused(
                    "SECRET_KEY",
                    DEBUG=value,
                    SECRET_KEY="weak",
                    ALLOWED_HOSTS="a.example.com",
                )

    def test_recognised_debug_values_allow_a_dev_setup(self):
        for value in ("1", "true", "True", "TRUE", "yes", "on", "On"):
            with self.subTest(value=value):
                out = self.load(DEBUG=value, SECRET_KEY="", ALLOWED_HOSTS="")
                self.assertIs(out["DEBUG"], True)

    def test_non_numeric_hsts_seconds_fails_at_startup(self):
        result = run(
            PROBE,
            DEBUG="False",
            SECRET_KEY=strong_key(),
            ALLOWED_HOSTS="a.example.com",
            SECURE_HSTS_SECONDS="a lot",
        )
        self.assertNotEqual(result.returncode, 0)


class ProductionDefaultsTests(ProbeMixin, SimpleTestCase):
    def prod(self, **extra):
        return self.load(
            DEBUG="False",
            SECRET_KEY=strong_key(),
            ALLOWED_HOSTS="a.example.com",
            **extra,
        )

    def test_https_and_cookie_defaults_are_secure(self):
        out = self.prod()
        self.assertIs(out["SECURE_SSL_REDIRECT"], True)
        self.assertIs(out["SESSION_COOKIE_SECURE"], True)
        self.assertIs(out["CSRF_COOKIE_SECURE"], True)
        self.assertEqual(out["SECURE_HSTS_SECONDS"], 31536000)
        self.assertIs(out["SECURE_HSTS_INCLUDE_SUBDOMAINS"], True)
        self.assertIs(out["SECURE_HSTS_PRELOAD"], True)

    def test_allowed_hosts_are_split_and_trimmed(self):
        out = self.load(
            DEBUG="False",
            SECRET_KEY=strong_key(),
            ALLOWED_HOSTS=" api.example.com , ,www.example.com,  ",
        )
        self.assertEqual(out["ALLOWED_HOSTS"], ["api.example.com", "www.example.com"])

    def test_each_secure_default_can_be_overridden_explicitly(self):
        out = self.prod(
            SECURE_SSL_REDIRECT="false",
            SESSION_COOKIE_SECURE="0",
            CSRF_COOKIE_SECURE="no",
            SECURE_HSTS_SECONDS="60",
            SECURE_HSTS_INCLUDE_SUBDOMAINS="off",
            SECURE_HSTS_PRELOAD="false",
        )
        self.assertIs(out["SECURE_SSL_REDIRECT"], False)
        self.assertIs(out["SESSION_COOKIE_SECURE"], False)
        self.assertIs(out["CSRF_COOKIE_SECURE"], False)
        self.assertEqual(out["SECURE_HSTS_SECONDS"], 60)
        self.assertIs(out["SECURE_HSTS_INCLUDE_SUBDOMAINS"], False)
        self.assertIs(out["SECURE_HSTS_PRELOAD"], False)

    def test_debug_mode_does_not_force_https_or_hsts(self):
        out = self.load(DEBUG="True", SECRET_KEY="dev-only", ALLOWED_HOSTS="localhost")
        self.assertIs(out["SECURE_SSL_REDIRECT"], False)
        self.assertIs(out["SESSION_COOKIE_SECURE"], False)
        self.assertIs(out["CSRF_COOKIE_SECURE"], False)
        self.assertEqual(out["SECURE_HSTS_SECONDS"], 0)

    def test_djangos_own_deploy_check_finds_no_https_or_secret_warnings(self):
        result = run(
            DEPLOY_CHECK,
            DEBUG="False",
            SECRET_KEY=strong_key(),
            ALLOWED_HOSTS="api.example.com",
        )
        output = result.stdout + result.stderr
        for check_id in (
            "security.W004",  # HSTS seconds
            "security.W005",  # HSTS subdomains
            "security.W008",  # SSL redirect
            "security.W009",  # weak SECRET_KEY
            "security.W012",  # session cookie secure
            "security.W016",  # csrf cookie secure
            "security.W018",  # DEBUG on
            "security.W020",  # empty ALLOWED_HOSTS
            "security.W021",  # HSTS preload
        ):
            with self.subTest(check_id):
                self.assertNotIn(check_id, output)


class DatabaseUrlTests(ProbeMixin, SimpleTestCase):
    def test_postgres_urls_are_parsed(self):
        for scheme in ("postgres", "postgresql"):
            with self.subTest(scheme):
                out = self.load(
                    DEBUG="True",
                    DATABASE_URL=f"{scheme}://dbuser:dbpass@db.internal:6543/jobs",
                )
                self.assertIn("postgresql", out["DB"]["ENGINE"])
                self.assertEqual(out["DB"]["NAME"], "jobs")
                self.assertEqual(out["DB"]["USER"], "dbuser")
                self.assertEqual(out["DB"]["HOST"], "db.internal")
                self.assertEqual(out["DB"]["PORT"], "6543")

    def test_other_database_schemes_are_refused(self):
        for url in ("sqlite:///db.sqlite3", "mysql://u:p@h/db", "not a url"):
            with self.subTest(url):
                result = run(PROBE, DEBUG="True", DATABASE_URL=url)
                self.assertNotEqual(result.returncode, 0)

    def test_individual_db_variables_used_when_no_url(self):
        out = self.load(DEBUG="True")
        self.assertEqual(out["DB"]["NAME"], DB_DEFAULTS["DB_NAME"])
        self.assertEqual(out["DB"]["HOST"], DB_DEFAULTS["DB_HOST"])


class KnownWeakKeyGaps(ProbeMixin, SimpleTestCase):
    """EXPECTED TO FAIL against the current check (length < 50 or 3 exact strings).

    Django's startproject writes keys that start with 'django-insecure-' and are
    longer than 50 characters, and a 60-character run of one letter is not secret.
    Both pass today. Tighten the check, then these go green.
    """

    def test_startproject_default_style_key_refused(self):
        self.assert_refused(
            "SECRET_KEY",
            DEBUG="False",
            SECRET_KEY="django-insecure-" + secrets.token_urlsafe(40),
            ALLOWED_HOSTS="api.example.com",
        )

    def test_low_entropy_key_refused(self):
        self.assert_refused(
            "SECRET_KEY",
            DEBUG="False",
            SECRET_KEY="a" * 60,
            ALLOWED_HOSTS="api.example.com",
        )
