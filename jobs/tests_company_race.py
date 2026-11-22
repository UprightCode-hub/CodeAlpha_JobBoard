"""Company creation race: a lost OneToOne insert race must be a clean 400.

Drop into jobs/. Run: python manage.py test jobs.tests_company_race

The first two classes simulate the race deterministically. The last class fires
real concurrent requests (needs PostgreSQL, which this project already uses).
"""

import threading
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections, transaction
from django.db.models.query import QuerySet
from django.test import TransactionTestCase
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from jobs.models import Company
from jobs.serializers import CompanySerializer

User = get_user_model()


def make_user(username, role="employer"):
    return User.objects.create(
        username=username, email=f"{username}@example.com", role=role
    )


class SimulatedRaceTests(APITestCase):
    def setUp(self):
        self.url = reverse("company")
        self.emp = make_user("emp")
        self.client.force_authenticate(user=self.emp)

    def lose_the_race(self):
        """Make the 'does this employer already have a company?' pre-check lie once.

        The winner's row already exists, so the INSERT hits the real OneToOne
        unique constraint, exactly like two simultaneous requests would.
        """
        real_exists = QuerySet.exists
        state = {"lied": False}

        def exists(queryset):
            if queryset.model is Company and not state["lied"]:
                state["lied"] = True
                return False
            return real_exists(queryset)

        return patch.object(QuerySet, "exists", exists), state

    def test_losing_the_insert_race_is_a_clean_400(self):
        Company.objects.create(owner=self.emp, name="Winner", description="first")
        patcher, state = self.lose_the_race()
        with patcher:
            r = self.client.post(
                self.url, {"name": "Loser", "description": "second"}, format="json"
            )
        self.assertEqual(r.status_code, 400, r.content[:400])
        body = r.json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(body["error"]["code"], "validation_error")
        text = r.content.decode().lower()
        for leak in ("constraint", "duplicate key", "integrity", "traceback", "unique"):
            self.assertNotIn(leak, text)
        self.assertEqual(Company.objects.filter(owner=self.emp).count(), 1)
        self.assertEqual(Company.objects.get(owner=self.emp).name, "Winner")

    def test_the_view_still_works_after_the_failed_insert(self):
        Company.objects.create(owner=self.emp, name="Winner", description="first")
        patcher, _ = self.lose_the_race()
        with patcher:
            self.client.post(
                self.url, {"name": "Loser", "description": "x"}, format="json"
            )
        # the transaction must not be left broken
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["name"], "Winner")

    def test_an_unrelated_integrity_error_is_still_a_server_error(self):
        """Only the duplicate-company case may become 400.

        Anything else is a real bug.
        """
        with patch.object(
            CompanySerializer,
            "save",
            side_effect=IntegrityError("violates constraint secret_internal_name"),
        ):
            with self.assertLogs("django.request", level="ERROR"):
                r = self.client.post(
                    self.url, {"name": "Acme", "description": "d"}, format="json"
                )
        self.assertEqual(r.status_code, 500)
        body = r.json()
        self.assertEqual(body["error"]["code"], "server_error")
        self.assertEqual(set(body["error"]), {"code", "message"})
        self.assertNotIn("secret_internal_name", r.content.decode())
        self.assertEqual(Company.objects.count(), 0)

    def test_plain_duplicate_is_400_without_any_race(self):
        Company.objects.create(owner=self.emp, name="First", description="d")
        r = self.client.post(
            self.url, {"name": "Second", "description": "d"}, format="json"
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "validation_error")
        self.assertEqual(Company.objects.count(), 1)

    def test_owner_in_body_is_ignored(self):
        other = make_user("other")
        r = self.client.post(
            self.url,
            {"name": "Mine", "description": "d", "owner": other.pk},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.content[:300])
        self.assertEqual(Company.objects.get(name="Mine").owner, self.emp)
        self.assertFalse(Company.objects.filter(owner=other).exists())


class DatabaseConstraintTests(APITestCase):
    def test_one_company_per_owner_is_enforced_by_the_database(self):
        emp = make_user("emp")
        Company.objects.create(owner=emp, name="A", description="d")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Company.objects.create(owner=emp, name="B", description="d")
        self.assertEqual(Company.objects.filter(owner=emp).count(), 1)


class ConcurrentCompanyCreateTests(TransactionTestCase):
    """Real threads, real connections. Any interleaving must give exactly one 201."""

    ROUNDS = 6
    THREADS = 4

    def test_simultaneous_creates_give_one_201_and_no_500(self):
        url = reverse("company")
        for round_number in range(self.ROUNDS):
            emp = make_user(f"racer{round_number}")
            barrier = threading.Barrier(self.THREADS)
            statuses = []
            errors = []

            def worker(
                index,
                emp=emp,
                barrier=barrier,
                round_number=round_number,
                statuses=statuses,
                errors=errors,
            ):
                try:
                    client = APIClient()
                    client.force_authenticate(user=emp)
                    barrier.wait(timeout=10)
                    r = client.post(
                        url,
                        {"name": f"Co {round_number}-{index}", "description": "d"},
                        format="json",
                    )
                    statuses.append(r.status_code)
                except Exception as exc:  # noqa: BLE001
                    errors.append(repr(exc))
                finally:
                    connections.close_all()

            threads = [
                threading.Thread(target=worker, args=(i,)) for i in range(self.THREADS)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            with self.subTest(round=round_number):
                self.assertEqual(errors, [])
                self.assertEqual(sorted(statuses), [201] + [400] * (self.THREADS - 1))
                self.assertEqual(Company.objects.filter(owner=emp).count(), 1)
