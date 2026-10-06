import warnings
from datetime import timedelta

from django.core.paginator import UnorderedObjectListWarning
from django.test import TestCase
from django.utils import timezone

from management.helpers.detailed_pagination import get_paginated_format_v2
from management.models.audience_filters import AudienceFilters
from management.models.community_events import CommunityEvent
from management.models.profile import Profile
from management.tests.helpers import register_user


def _event(**overrides) -> CommunityEvent:
    fields = {
        "title": "Event",
        "description": "Description",
        "time": timezone.now(),
        "active": True,
        "custom_filter": AudienceFilters.NONE,
    }
    fields.update(overrides)
    return CommunityEvent.objects.create(**fields)


class CommunityEventOrderingTest(TestCase):
    def setUp(self):
        self.user = register_user()

    def test_paginated_user_events_are_ordered(self):
        base = timezone.now()
        for hours in (5, 1, 3):
            _event(time=base + timedelta(hours=hours))

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            get_paginated_format_v2(CommunityEvent.get_active_events_for_user(self.user), 2, 1)

        unordered = [w for w in caught if issubclass(w.category, UnorderedObjectListWarning)]
        self.assertEqual(unordered, [])

    def test_events_ordered_by_time_and_id(self):
        base = timezone.now()
        first = _event(time=base + timedelta(hours=1))
        second = _event(time=base + timedelta(hours=2))
        third = _event(time=base + timedelta(hours=3))

        times = list(CommunityEvent.get_active_events_for_user(self.user).values_list("time", flat=True))
        self.assertEqual(times, sorted(times))

        page_one = list(get_paginated_format_v2(CommunityEvent.get_active_events_for_user(self.user), 2, 1)["results"])
        page_two = list(get_paginated_format_v2(CommunityEvent.get_active_events_for_user(self.user), 2, 2)["results"])
        self.assertEqual(page_one, [first, second])
        self.assertEqual(page_two, [third])
        self.assertEqual({e.id for e in page_one} & {e.id for e in page_two}, set())

    def test_filter_events_stay_ordered_after_combine(self):
        base = timezone.now()
        no_filter = _event(time=base + timedelta(hours=1))
        matching = _event(time=base, custom_filter=AudienceFilters.LEARNERS)
        _event(time=base + timedelta(hours=2), custom_filter=AudienceFilters.VOLUNTEERS)

        events = list(CommunityEvent.get_active_events_for_user(self.user))
        self.assertIn(no_filter, events)
        self.assertIn(matching, events)
        self.assertEqual([e.id for e in events], [matching.id, no_filter.id])

    def test_identical_time_is_tie_broken_by_id(self):
        same_time = timezone.now()
        first = _event(time=same_time)
        second = _event(time=same_time)

        events = list(CommunityEvent.get_active_events_for_user(self.user))
        self.assertEqual([e.id for e in events], [first.id, second.id])

    def test_onboarded_filters_require_matching_type_and_onboarding(self):
        learner_event = _event(custom_filter=AudienceFilters.ONBOARDED_LEARNERS)
        volunteer_event = _event(custom_filter=AudienceFilters.ONBOARDED_VOLUNTEERS)

        self.assertNotIn(learner_event, CommunityEvent.get_active_events_for_user(self.user))

        self.user.state.is_onboarded = True
        self.user.state.save(update_fields=["is_onboarded"])
        self.assertIn(learner_event, CommunityEvent.get_active_events_for_user(self.user))
        self.assertNotIn(volunteer_event, CommunityEvent.get_active_events_for_user(self.user))

        self.user.profile.user_type = Profile.TypeChoices.VOLUNTEER
        self.user.profile.save(update_fields=["user_type"])
        self.assertNotIn(learner_event, CommunityEvent.get_active_events_for_user(self.user))
        self.assertIn(volunteer_event, CommunityEvent.get_active_events_for_user(self.user))

    def test_registered_filter_labels_are_unambiguous(self):
        self.assertEqual(AudienceFilters.LEARNERS.label, "All registered learners")
        self.assertEqual(AudienceFilters.VOLUNTEERS.label, "All registered volunteers")
