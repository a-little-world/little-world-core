from django.test import SimpleTestCase

from management.analytics.user_journey.catalog import CATALOG as UJ_CATALOG
from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
from management.api.user_advanced_filter_lists import (
    ANALYTICS_FILTER_LISTS,
    FILTER_LISTS,
    USER_JOURNEY_FILTER_LISTS,
    category_for_list_id,
)


class FilterListPickerLabelTests(SimpleTestCase):
    def test_user_journey_v5_labels_use_category_and_catalog_title(self):
        entry = next(item for item in FILTER_LISTS if item.name == "state__gave_up")
        self.assertEqual(entry.category(), "User Journey")
        self.assertEqual(entry.resolved_display_name(), UJ_CATALOG["state__gave_up"].display_name)
        self.assertEqual(entry.picker_label(), f"User Journey - {UJ_CATALOG['state__gave_up'].display_name}")
        payload = entry.to_dict()
        self.assertEqual(payload["label"], entry.picker_label())
        self.assertEqual(payload["description"], UJ_CATALOG["state__gave_up"].description)

    def test_communications_lists_are_prefixed(self):
        entry = next(item for item in FILTER_LISTS if item.name == "message_reply_required")
        self.assertEqual(entry.category(), "Communications")
        self.assertTrue(entry.picker_label().startswith("Communications - "))

    def test_legacy_user_journey_lists_sit_after_v5(self):
        names = [entry.name for entry in FILTER_LISTS]
        v5_ids = [entry.name for entry in ANALYTICS_FILTER_LISTS]
        v4_ids = [entry.name for entry in USER_JOURNEY_FILTER_LISTS if entry.name.startswith("journey_v2__")]
        last_v5 = max(names.index(list_id) for list_id in v5_ids)
        first_v4 = min(names.index(list_id) for list_id in v4_ids)
        self.assertLess(last_v5, first_v4)

    def test_legacy_match_journey_lists_sit_after_v5(self):
        names = [entry.name for entry in MATCH_JOURNEY_FILTERS]
        v5_ids = [name for name in names if name.startswith(("match_state__", "match_funnel__"))]
        v4_ids = [name for name in names if name.startswith("match_journey_v2__")]
        last_v5 = max(names.index(list_id) for list_id in v5_ids)
        first_v4 = min(names.index(list_id) for list_id in v4_ids)
        self.assertLess(last_v5, first_v4)
        self.assertEqual(category_for_list_id("match_state__unviewed"), "Match Journey")
        self.assertEqual(category_for_list_id("match_journey_v2__unviewed"), "Match Journey V4")
