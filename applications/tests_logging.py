"""Tests that unexpected server errors are hidden from clients and logged."""
from unittest.mock import patch

from django.conf import settings
from django.db.models.query import QuerySet
from rest_framework.test import APITestCase


class ServerErrorLoggingTests(APITestCase):
    def test_crash_returns_clean_json_and_logs_the_traceback(self):
        # Force an unexpected error deep inside a normal request.
        with patch.object(QuerySet, "__iter__", side_effect=RuntimeError("secret-internal-detail")):
            with self.assertLogs("django.request", level="ERROR") as logs:
                response = self.client.get("/api/jobs/")

        self.assertEqual(response.status_code, 500)
        body = response.json()
        self.assertEqual(body["error"]["code"], "server_error")
        # The client must never see the internal detail.
        self.assertNotIn("secret-internal-detail", response.content.decode())
        # The server log must have it, with a traceback.
        self.assertTrue(any(record.exc_info for record in logs.records))
        self.assertIn("secret-internal-detail", "\n".join(logs.output))

    def test_settings_send_server_errors_to_a_console_handler(self):
        loggers = settings.LOGGING["loggers"]
        self.assertIn("django.request", loggers)
        handler_names = loggers["django.request"]["handlers"]
        self.assertTrue(handler_names)
        for name in handler_names:
            self.assertIn(name, settings.LOGGING["handlers"])
            self.assertEqual(
                settings.LOGGING["handlers"][name]["class"], "logging.StreamHandler"
            )
