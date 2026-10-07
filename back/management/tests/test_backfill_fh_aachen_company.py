from io import StringIO
from uuid import uuid4

from django.conf import settings
from django.core.management import call_command
from django.test import TestCase

from management.api.user_advanced_filter import EXTRA__fh_aachen_users
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
        semester_user = _user("fh-aachen-so26")
        unrelated_user = _user("other-company")

        out = StringIO()
        call_command("backfill_fh_aachen_company", stdout=out)

        legacy_user.state.refresh_from_db()
        semester_user.state.refresh_from_db()
        unrelated_user.state.refresh_from_db()

        self.assertEqual(legacy_user.state.company, "fh-aachen-wi2627")
        self.assertEqual(legacy_user.state.past_companies, ["fh-aachen"])
        self.assertEqual(semester_user.state.company, "fh-aachen-so26")
        self.assertEqual(unrelated_user.state.company, "other-company")
        self.assertIn("changed=1", out.getvalue())

    def test_dry_run_does_not_write(self):
        user = _user("fh-aachen")

        out = StringIO()
        call_command("backfill_fh_aachen_company", "--dry-run", stdout=out)

        user.state.refresh_from_db()
        self.assertEqual(user.state.company, "fh-aachen")
        self.assertEqual(user.state.past_companies, [])
        self.assertIn("DRY RUN: would_change=1", out.getvalue())

    def test_is_idempotent(self):
        user = _user("fh-aachen")

        call_command("backfill_fh_aachen_company", stdout=StringIO())
        call_command("backfill_fh_aachen_company", stdout=StringIO())

        user.state.refresh_from_db()
        self.assertEqual(user.state.company, "fh-aachen-wi2627")
        self.assertEqual(user.state.past_companies, ["fh-aachen"])

    def test_backfilled_users_keep_company_benefits(self):
        user = _user("fh-aachen")

        call_command("backfill_fh_aachen_company", stdout=StringIO())

        user.state.refresh_from_db()
        # Mirrors the `.lower() in` checks in controller.create_user and ProfileCompletedApi
        self.assertIn(user.state.company.lower(), settings.CUSTOM_ONBOARDING_COMPANIES)
        self.assertIn(user.state.company.lower(), settings.MATCH_PRIORITY_COMPANIES)

    def test_fh_aachen_filter_includes_cohorts(self):
        legacy_user = _user("fh-aachen")
        semester_user = _user("fh-aachen-so26")
        lookalike_user = _user("fh-aachenxyz")
        unrelated_user = _user("other-company")

        users = set(EXTRA__fh_aachen_users())

        self.assertIn(legacy_user, users)
        self.assertIn(semester_user, users)
        self.assertNotIn(lookalike_user, users)
        self.assertNotIn(unrelated_user, users)


class CompanySettingsTests(TestCase):
    def test_company_lists_are_lowercase(self):
        """Company checks compare `company.lower()` against these lists, so mixed-case entries never match."""
        for setting_name in [
            "CUSTOM_ONBOARDING_COMPANIES",
            "MATCH_PRIORITY_COMPANIES",
            "SKIP_EMAIL_VERIFICATION_COMPANIES",
            "FORCE_MATCH_ELIGIBLE_COMPANIES",
        ]:
            for company in getattr(settings, setting_name):
                self.assertEqual(company, company.lower(), f"{setting_name} entry {company!r} must be lowercase")
