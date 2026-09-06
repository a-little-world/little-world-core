"""Both people on a call get asked, not just whoever hung up last.

The offer used to be made per ``participant_left`` event. ``session.end_time`` is only
assigned once *both* participants are gone, and ``offer_post_call_survey`` returns early
while it is None — so the first person to leave was skipped silently. No error, no row, and
roughly half of every call's feedback missing.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from management.models.survey import (
    QUALIFYING_CALL_MIN_DURATION,
    SurveyCampaign,
    SurveyResponse,
    localized,
)
from management.models.user import User
from video.livekit_webhook import process_webhook_classic_call__participant_left
from video.models import LiveKitRoom, LivekitSession, LivekitWebhookEvent

#: A call too short to qualify, expressed against the rule rather than in minutes, so tuning
#: `QUALIFYING_CALL_MIN_DURATION` moves the test with it.
NON_QUALIFYING_CALL = QUALIFYING_CALL_MIN_DURATION / 2


class PostCallSurveyOfferTests(TestCase):
    def setUp(self):
        self.u1 = User.objects.create_user(email="left-first@test.de", password="x", first_name="A", last_name="A")
        self.u2 = User.objects.create_user(email="left-last@test.de", password="x", first_name="B", last_name="B")
        self.room = LiveKitRoom.objects.create(u1=self.u1, u2=self.u2)
        self.event = LivekitWebhookEvent.objects.create(data={})

        self.campaign = self._campaign("post-call", "Post-call feedback")

    def _campaign(
        self,
        slug: str,
        name: str,
        trigger: str = SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
    ) -> SurveyCampaign:
        campaign = SurveyCampaign(
            slug=slug,
            name=name,
            copy={
                "title": localized(de="Wie war der Call?"),
                "description": localized(),
                "submit_button": localized(de="Absenden"),
            },
            scale=5,
            questions=[{"id": "rating", "type": "rating", "required": True, "label": localized(de="Bewertung")}],
            trigger=trigger,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
            active=True,
        )
        campaign.save()
        return campaign

    def _session(self, *, duration: timedelta) -> LivekitSession:
        # Both flags on: they are *in* the call. The handler clears one per leave event and
        # only treats the call as over once neither is active.
        session = LivekitSession.objects.create(
            room=self.room,
            u1=self.u1,
            u2=self.u2,
            both_have_been_active=True,
            is_active=True,
            u1_active=True,
            u2_active=True,
        )
        LivekitSession.objects.filter(pk=session.pk).update(created_at=timezone.now() - duration)
        session.refresh_from_db()
        return session

    def _leave(self, user):
        with patch("video.livekit_webhook.InBlockIncomingCall"):
            process_webhook_classic_call__participant_left(
                {}, self.event, str(user.uuid), user, str(self.room.uuid), self.room
            )

    def _offered_to(self):
        return set(SurveyResponse.objects.filter(campaign=self.campaign).values_list("user_id", flat=True))

    def test_both_participants_are_offered_the_survey(self):
        self._session(duration=NON_QUALIFYING_CALL)

        self._leave(self.u1)
        self._leave(self.u2)

        self.assertEqual(self._offered_to(), {self.u1.pk, self.u2.pk})

    def test_nothing_is_offered_until_the_call_actually_ends(self):
        """One person still in the room means the call is not over."""
        self._session(duration=NON_QUALIFYING_CALL)

        self._leave(self.u1)

        self.assertEqual(self._offered_to(), set())

    def test_a_call_at_the_threshold_goes_to_the_other_trigger(self):
        """The split is `>= QUALIFYING_CALL_MIN_DURATION`, so the threshold itself qualifies.

        Timed off the constant rather than a number written here: the rule lives in
        `offer_post_call_survey`, and a test that restates it stops testing the rule the
        moment somebody tunes it.
        """
        self._session(duration=QUALIFYING_CALL_MIN_DURATION)

        self._leave(self.u1)
        self._leave(self.u2)

        self.assertEqual(self._offered_to(), set())

    def test_every_after_a_call_campaign_offers_to_everyone(self):
        """N campaigns on this trigger produce N offers per participant, not one between them.

        Worth pinning because delivery is serialised: `pending_survey_for_user` hands back one
        card and then the user-wide cooldown closes the door, so a second campaign's card
        waits at least `SHOW_COOLDOWN` behind the first. Two context-scoped campaigns create
        offers faster than one call per cooldown window can drain them.
        """
        second = self._campaign("nps-after-call", "NPS after a call")
        self._session(duration=NON_QUALIFYING_CALL)

        self._leave(self.u1)
        self._leave(self.u2)

        for campaign in (self.campaign, second):
            offered = set(SurveyResponse.objects.filter(campaign=campaign).values_list("user_id", flat=True))
            self.assertEqual(offered, {self.u1.pk, self.u2.pk}, f"{campaign.slug} missed a participant")

        self.assertEqual(SurveyResponse.objects.count(), 4)

    def test_a_qualifying_call_goes_to_the_qualifying_campaign(self):
        """A real conversation is asked how it went, not what went wrong.

        The two triggers partition every finished standard call at
        `QUALIFYING_CALL_MIN_DURATION`, so exactly one campaign is offered — the length of
        the call decides which.
        """
        qualifying = self._campaign(
            "post-qualifying-call", "After a qualifying call", trigger=SurveyCampaign.Trigger.QUALIFYING_CALL_ENDED
        )
        self._session(duration=QUALIFYING_CALL_MIN_DURATION)

        self._leave(self.u1)
        self._leave(self.u2)

        self.assertEqual(
            set(SurveyResponse.objects.filter(campaign=qualifying).values_list("user_id", flat=True)),
            {self.u1.pk, self.u2.pk},
        )
        self.assertFalse(
            SurveyResponse.objects.filter(campaign=self.campaign).exists(),
            "a qualifying call must not fire the non-qualifying campaign",
        )
