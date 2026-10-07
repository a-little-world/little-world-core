from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase

from management.models.user import User


def _user(company):
    user = User.objects.create_user(
        email=f"fh-aachen-backfill-{uuid4()}@example.com",
        password="Test123!",
        first_name="Test",
        last_name="User",
    )
    user.state.company = company
    user.state.save(update_fields=["company"])
    return user


class BackfillFhAachenCompanyTests(TestCase):
    def test_changes_only_legacy_company_and_retains_history(self):
        legacy_user = _user("fh-aachen")
        semester_user = _user("fh-aachen-So26")
        unrelated_user = _user("other-company")

        out = StringIO()
        call_command("backfill_fh_aachen_company", stdout=out)

        legacy_user.state.refresh_from_db()
        semester_user.state.refresh_from_db()
        unrelated_user.state.refresh_from_db()

        self.assertEqual(legacy_user.state.company, "fh-aachen-Wi2627")
        self.assertEqual(legacy_user.state.past_companies, ["fh-aachen"])
        self.assertEqual(semester_user.state.company, "fh-aachen-So26")
        self.assertEqual(unrelated_user.state.company, "other-company")
        self.assertIn("changed=1", out.getvalue())

    def test_dry_run_does_not_write(self):
        user = _user("fh-aachen")

        out = StringIO()
        call_command("backfill_fh_aachen_company", "--dry-run", stdout=out)

        user.state.refresh_from_db()
        self.assertEqual(user.state.company, "fh-aachen")
        self.assertEqual(user.state.past_companies, [])
        self.assertIn("DRY RUN: changed=1", out.getvalue())

    def test_is_idempotent(self):
        user = _user("fh-aachen")

        call_command("backfill_fh_aachen_company", stdout=StringIO())
        call_command("backfill_fh_aachen_company", stdout=StringIO())

        user.state.refresh_from_db()
        self.assertEqual(user.state.company, "fh-aachen-Wi2627")
        self.assertEqual(user.state.past_companies, ["fh-aachen"])
