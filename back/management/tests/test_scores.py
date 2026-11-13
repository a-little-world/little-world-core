from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from management.api.scores import ScoringBase


def _user(company):
    return SimpleNamespace(
        state=SimpleNamespace(company=company),
        profile=SimpleNamespace(availability={}),
    )


@override_settings(SCORES_DISABLED_TIME_OVERLAP=["fh-aachen"])
class TimeSlotOverlapCompanyPrefixTests(SimpleTestCase):
    def test_disables_overlap_for_semester_suffixed_companies(self):
        scoring = ScoringBase(_user("fh-aachen-so26"), _user("fh-aachen-wi2627"))

        result = scoring.score__time_slot_overlap()

        self.assertTrue(result.matchable)
        self.assertEqual(result.score, 0)
        self.assertIn("disabled", result.markdown_info)

    def test_does_not_disable_overlap_when_only_one_company_matches(self):
        scoring = ScoringBase(_user("fh-aachen-wi2627"), _user("other-company"))

        result = scoring.score__time_slot_overlap()

        self.assertFalse(result.matchable)

    def test_disables_overlap_for_base_company_case_insensitively(self):
        scoring = ScoringBase(_user("fh-aachen"), _user("FH-Aachen-WI2627"))

        result = scoring.score__time_slot_overlap()

        self.assertTrue(result.matchable)
        self.assertEqual(result.score, 0)

    def test_does_not_disable_overlap_for_lookalike_companies(self):
        scoring = ScoringBase(_user("fh-aachenxyz"), _user("fh-aachen-so26"))

        result = scoring.score__time_slot_overlap()

        self.assertFalse(result.matchable)

    def test_handles_users_without_a_company(self):
        scoring = ScoringBase(_user(None), _user(None))

        result = scoring.score__time_slot_overlap()

        self.assertFalse(result.matchable)
