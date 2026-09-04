from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from video.models import LiveKitRoom, LivekitSession

from management import surveys
from management.models.survey import (
    QUALIFYING_CALL_MIN_DURATION,
    SurveyCampaign,
    SurveyResponse,
    localized,
)
from management.tests.helpers import register_user


def _minutes(duration) -> int:
    """Whole minutes of a rule constant, so the tests move when the rule does."""
    return int(duration.total_seconds() // 60)


def _campaign(**overrides) -> SurveyCampaign:
    """Build a campaign, reusing the slug if a migration already seeded it (e.g. post-call)."""
    fields = {
        "slug": "test-campaign",
        "name": "Test campaign",
        "copy": {
            "title": localized(de="Wie gefällt es dir?", en="How are you finding it?"),
            "description": localized(de="Kurz gefragt.", en="Quick question."),
            "submit_button": localized(de="Absenden", en="Submit"),
        },
        "scale": 5,
        "questions": [
            {"id": "rating", "type": "rating", "required": True, "label": localized(de="Bewertung", en="Rating")},
            {"id": "comment", "type": "text", "required": False, "label": localized(de="Kommentar", en="Comment")},
        ],
        "active": True,
    }
    fields.update(overrides)
    campaign = SurveyCampaign.objects.filter(slug=fields["slug"]).first() or SurveyCampaign()
    for field, value in fields.items():
        setattr(campaign, field, value)
    campaign.save()
    return campaign


def _q(qid: str, qtype: str, *, required: bool = False, **extra) -> dict:
    """A question with copy in both languages, matching the bilingual campaign `_campaign`
    builds — a campaign that has English copy must have it everywhere."""
    return {"id": qid, "type": qtype, "required": required, "label": localized(de=qid, en=qid), **extra}


def _choice(value: str) -> dict:
    return {"value": value, "label": localized(de=value, en=value)}


def _finished_session(user, partner, *, minutes=5) -> LivekitSession:
    room = LiveKitRoom.objects.create(u1=user, u2=partner)
    session = LivekitSession.objects.create(
        room=room,
        u1=user,
        u2=partner,
        both_have_been_active=True,
        is_active=False,
        end_time=timezone.now(),
    )
    LivekitSession.objects.filter(pk=session.pk).update(created_at=session.end_time - timedelta(minutes=minutes))
    session.refresh_from_db()
    return session


class CampaignCopyTests(TestCase):
    """Copy is edited in the admin panel, so the model is the only thing standing between a
    half-filled form and a user reading a blank card."""

    def test_card_resolves_to_the_requested_language(self):
        card = _campaign().card_for("en")
        self.assertEqual(card["title"], "How are you finding it?")
        self.assertEqual([q["label"] for q in card["questions"]], ["Rating", "Comment"])

    def test_missing_english_falls_back_to_german(self):
        campaign = _campaign(
            questions=[{"id": "comment", "type": "text", "label": localized(de="Kommentar")}],
            copy={
                "title": localized(de="Nur Deutsch"),
                "description": localized(),
                "submit_button": localized(de="Absenden"),
            },
        )
        card = campaign.card_for("en")
        self.assertEqual(card["title"], "Nur Deutsch")
        self.assertEqual(card["questions"][0]["label"], "Kommentar")

    def test_rejects_underscore_in_slug(self):
        with self.assertRaises(ValidationError):
            _campaign(slug="bad_slug")

    def test_cannot_activate_without_german_copy(self):
        with self.assertRaises(ValidationError):
            _campaign(copy={"title": localized(en="English only"), "submit_button": localized(de="Absenden")})

    def test_can_save_an_incomplete_draft(self):
        campaign = _campaign(active=False, copy={"title": localized(), "submit_button": localized()})
        self.assertTrue(campaign.missing_copy())

    def test_partial_translation_blocks_activation(self):
        # A German title above an English question reads worse than plain German.
        with self.assertRaises(ValidationError):
            _campaign(
                questions=[{"id": "comment", "type": "text", "required": False, "label": localized(de="Nur Deutsch")}],
                copy={
                    "title": localized(de="Titel", en="Title"),
                    "submit_button": localized(de="Absenden", en="Submit"),
                },
            )

    def test_leftover_rating_labels_are_dropped_on_save(self):
        campaign = _campaign(copy={**_campaign().copy, "rating_labels": [localized(de="Schlecht")]})
        campaign.refresh_from_db()
        self.assertNotIn("rating_labels", campaign.copy)

    def test_option_labels_are_editable_after_answers(self):
        campaign = _campaign(
            questions=[
                {
                    "id": "reason",
                    "type": "choice",
                    "required": True,
                    "label": localized(de="Warum?"),
                    "options": [
                        {"value": "price", "label": localized(de="Preis")},
                        {"value": "people", "label": localized(de="Leute")},
                    ],
                }
            ],
            copy={
                "title": localized(de="Titel"),
                "description": localized(),
                "submit_button": localized(de="Absenden"),
            },
        )
        user = register_user()
        SurveyResponse.objects.create(campaign=campaign, user=user, answers={"reason": "price"})

        campaign.questions[0]["options"][0]["label"] = localized(de="Der Preis")
        campaign.save()
        self.assertEqual(campaign.card_for("de")["questions"][0]["options"][0]["label"], "Der Preis")

    def test_option_values_in_answers_are_still_frozen(self):
        campaign = _campaign(
            questions=[
                {
                    "id": "reason",
                    "type": "choice",
                    "required": True,
                    "label": localized(de="Warum?"),
                    "options": [
                        {"value": "price", "label": localized(de="Preis")},
                        {"value": "people", "label": localized(de="Leute")},
                    ],
                }
            ],
            copy={
                "title": localized(de="Titel"),
                "description": localized(),
                "submit_button": localized(de="Absenden"),
            },
        )
        user = register_user()
        SurveyResponse.objects.create(campaign=campaign, user=user, answers={"reason": "price"})

        campaign.questions[0]["options"] = [{"value": "people", "label": localized(de="Leute")}]
        with self.assertRaises(ValidationError):
            campaign.save()


class SurveyCampaignValidationTests(TestCase):
    def test_rejects_unknown_question_type(self):
        with self.assertRaises(ValidationError):
            _campaign(questions=[{"id": "rating", "type": "starz"}])

    def test_rejects_duplicate_question_ids(self):
        with self.assertRaises(ValidationError):
            _campaign(
                questions=[
                    {"id": "rating", "type": "rating"},
                    {"id": "rating", "type": "text"},
                ]
            )

    def test_rejects_choice_question_without_options(self):
        with self.assertRaises(ValidationError):
            _campaign(questions=[{"id": "reason", "type": "choice"}])

    def test_context_scope_requires_context_type(self):
        with self.assertRaises(ValidationError):
            _campaign(repeat_scope=SurveyCampaign.RepeatScope.CONTEXT)

    def test_context_scope_requires_an_event_trigger(self):
        # on_session delivery has no context to key an offer on, so this combination used to
        # raise straight out of the pending endpoint for every user.
        with self.assertRaises(ValidationError):
            _campaign(
                trigger=SurveyCampaign.Trigger.ON_SESSION,
                repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
                context_type=SurveyCampaign.ContextType.LIVE_SESSION,
            )

    def test_company_audience_requires_a_value(self):
        with self.assertRaises(ValidationError):
            _campaign(audience_type=SurveyCampaign.AudienceType.COMPANY)

    def test_filter_audience_rejects_an_unknown_filter(self):
        with self.assertRaises(ValidationError):
            _campaign(audience_type=SurveyCampaign.AudienceType.FILTER, audience_value="not_a_filter")


class AnsweredQuestionsAreImmutableTests(TestCase):
    """Validation sits on the model rather than in admin, so a shell or a management command
    cannot quietly make existing answers unreadable."""

    def setUp(self):
        self.user = register_user()
        self.campaign = _campaign()
        SurveyResponse.objects.create(
            campaign=self.campaign,
            user=self.user,
            answers={"rating": 4, "comment": "great"},
            rating=4,
            status=SurveyResponse.Status.SUBMITTED,
        )

    def test_cannot_remove_an_answered_question(self):
        self.campaign.questions = [_q("rating", "rating", required=True)]
        with self.assertRaises(ValidationError):
            self.campaign.save()

    def test_cannot_rename_an_answered_question(self):
        self.campaign.questions = [
            _q("rating", "rating", required=True),
            _q("feedback", "text"),
        ]
        with self.assertRaises(ValidationError):
            self.campaign.save()

    def test_cannot_change_the_type_of_an_answered_question(self):
        self.campaign.questions = [
            _q("rating", "rating", required=True),
            _q("comment", "choice", options=[_choice("yes")]),
        ]
        with self.assertRaises(ValidationError):
            self.campaign.save()

    def test_cannot_change_scale_once_a_rating_exists(self):
        self.campaign.scale = 3
        with self.assertRaises(ValidationError):
            self.campaign.save()
        self.campaign.refresh_from_db()
        self.campaign.scale = 10
        with self.assertRaises(ValidationError):
            self.campaign.save()

    def test_can_change_scale_when_nobody_has_rated(self):
        SurveyResponse.objects.filter(campaign=self.campaign).delete()
        SurveyResponse.objects.create(campaign=self.campaign, user=self.user, answers={})
        self.campaign.scale = 7
        self.campaign.save()
        self.assertEqual(self.campaign.scale, 7)

    def test_can_add_a_question_and_reorder(self):
        self.campaign.questions = [
            _q("comment", "text", required=True),
            _q("rating", "rating", required=True),
            _q("reason", "choice", options=[_choice("price")]),
        ]
        self.campaign.save()
        self.assertEqual(len(self.campaign.questions), 3)

    def test_can_remove_a_question_nobody_answered(self):
        self.campaign.questions = [
            _q("rating", "rating", required=True),
            _q("comment", "text"),
            _q("spare", "text"),
        ]
        self.campaign.save()

        self.campaign.questions = self.campaign.questions[:2]
        self.campaign.save()
        self.assertEqual([q["id"] for q in self.campaign.questions], ["rating", "comment"])


class SurveyOfferTests(TestCase):
    def setUp(self):
        self.user = register_user()
        self.partner = register_user()

    def test_company_audience_matches_case_insensitively(self):
        campaign = _campaign(audience_type=SurveyCampaign.AudienceType.COMPANY, audience_value="acme")
        self.user.state.company = "ACME"
        self.user.state.save()
        self.assertTrue(surveys.user_matches_audience(campaign, self.user))

        self.user.state.company = "other"
        self.user.state.save()
        self.assertFalse(surveys.user_matches_audience(campaign, self.user))

    def test_filter_audience_uses_the_banner_filters(self):
        campaign = _campaign(
            audience_type=SurveyCampaign.AudienceType.FILTER,
            audience_value="volunteers",
        )
        self.assertFalse(surveys.user_matches_audience(campaign, self.user))
        volunteer = register_user()
        volunteer.profile.user_type = "volunteer"
        volunteer.profile.save()
        self.assertTrue(surveys.user_matches_audience(campaign, volunteer))

    def test_first_qualifying_call_is_required(self):
        campaign = _campaign(
            eligible_after_event=SurveyCampaign.EligibleAfterEvent.FIRST_QUALIFYING_CALL,
        )
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        _finished_session(self.user, self.partner, minutes=_minutes(QUALIFYING_CALL_MIN_DURATION))
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

    def test_a_longer_call_still_qualifies(self):
        """The rule is a floor. A long conversation is more evidence of a call, not less."""
        campaign = _campaign(
            eligible_after_event=SurveyCampaign.EligibleAfterEvent.FIRST_QUALIFYING_CALL,
        )
        _finished_session(self.user, self.partner, minutes=_minutes(QUALIFYING_CALL_MIN_DURATION) * 4)
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

    def test_short_calls_do_not_qualify(self):
        campaign = _campaign(
            eligible_after_event=SurveyCampaign.EligibleAfterEvent.FIRST_QUALIFYING_CALL,
        )
        _finished_session(self.user, self.partner, minutes=_minutes(QUALIFYING_CALL_MIN_DURATION) - 1)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

    def test_random_calls_do_not_count_as_qualifying(self):
        campaign = _campaign(
            eligible_after_event=SurveyCampaign.EligibleAfterEvent.FIRST_QUALIFYING_CALL,
        )
        session = _finished_session(self.user, self.partner, minutes=_minutes(QUALIFYING_CALL_MIN_DURATION))
        LivekitSession.objects.filter(pk=session.pk).update(random_call_session=True)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

    def test_onboarded_is_immediate(self):
        campaign = _campaign(eligible_after_event=SurveyCampaign.EligibleAfterEvent.ONBOARDED)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        self.user.state.is_onboarded = True
        self.user.state.save()
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

    def test_match_created_is_any_active_match(self):
        from django.db.models import Q

        from management.models.matches import Match

        Match.objects.filter(Q(user1=self.user) | Q(user2=self.user)).delete()
        campaign = _campaign(eligible_after_event=SurveyCampaign.EligibleAfterEvent.MATCH_CREATED)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        Match.objects.create(user1=self.user, user2=self.partner, support_matching=True)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        tandem = register_user()
        Match.objects.filter(Q(user1=tandem) | Q(user2=tandem)).delete()
        Match.objects.create(user1=self.user, user2=tandem)
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

    def test_match_success_is_any_successful_match_once_per_user(self):
        from django.db.models import Q

        from management.models.matches import Match

        Match.objects.filter(Q(user1=self.user) | Q(user2=self.user)).delete()
        campaign = _campaign(eligible_after_event=SurveyCampaign.EligibleAfterEvent.MATCH_SUCCESS)
        Match.objects.create(user1=self.user, user2=self.partner)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        other = register_user()
        Match.objects.filter(Q(user1=other) | Q(user2=other)).delete()
        Match.objects.create(user1=self.user, user2=other, completed_off_plattform=True)
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

        third = register_user()
        Match.objects.filter(Q(user1=third) | Q(user2=third)).delete()
        Match.objects.create(user1=self.user, user2=third, completed_off_plattform=True)
        first = surveys.pending_survey_for_user(self.user)
        second = surveys.pending_survey_for_user(self.user)
        self.assertIsNotNone(first)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SurveyResponse.objects.filter(campaign=campaign, user=self.user).count(), 1)

    def test_eligible_after_since_excludes_earlier_onboarding(self):
        self.user.state.is_onboarded = True
        self.user.state.onboarding_call_completed_at = timezone.now() - timedelta(days=400)
        self.user.state.save()
        campaign = _campaign(
            eligible_after_event=SurveyCampaign.EligibleAfterEvent.ONBOARDED,
            eligible_after_since=timezone.now() - timedelta(days=30),
        )
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        campaign.eligible_after_since = timezone.now() - timedelta(days=500)
        campaign.save()
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

    def test_eligible_after_since_uses_any_later_match(self):
        from django.db.models import Q

        from management.models.matches import Match

        Match.objects.filter(Q(user1=self.user) | Q(user2=self.user)).delete()
        old_partner = register_user()
        Match.objects.filter(Q(user1=old_partner) | Q(user2=old_partner)).delete()
        old = Match.objects.create(user1=self.user, user2=old_partner)
        Match.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=400))

        campaign = _campaign(
            eligible_after_event=SurveyCampaign.EligibleAfterEvent.MATCH_CREATED,
            eligible_after_since=timezone.now() - timedelta(days=30),
        )
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        new_partner = register_user()
        Match.objects.filter(Q(user1=new_partner) | Q(user2=new_partner)).delete()
        Match.objects.create(user1=self.user, user2=new_partner)
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

    def test_offer_is_idempotent(self):
        campaign = _campaign()
        first = surveys.offer_survey(campaign, self.user)
        second = surveys.offer_survey(campaign, self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(SurveyResponse.objects.filter(campaign=campaign).count(), 1)

    def test_answered_survey_is_not_offered_again(self):
        campaign = _campaign()
        response = surveys.offer_survey(campaign, self.user)
        surveys.submit_survey(response, {"rating": 5})
        self.assertIsNone(surveys.offer_survey(campaign, self.user))

    def test_dismissed_survey_is_not_offered_again(self):
        campaign = _campaign()
        surveys.dismiss_survey(surveys.offer_survey(campaign, self.user))
        self.assertIsNone(surveys.offer_survey(campaign, self.user))
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

    def test_post_call_survey_is_offered_once_per_session(self):
        campaign = _campaign(
            slug=surveys.POST_CALL_SLUG,
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        first_session = _finished_session(self.user, self.partner)
        second_session = _finished_session(self.user, self.partner)

        first = surveys.offer_post_call_survey(self.user, first_session)
        second = surveys.offer_post_call_survey(self.user, second_session)
        again = surveys.offer_post_call_survey(self.user, first_session)

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(first.pk, again.pk)
        self.assertEqual(first.context_key, f"live_session:{first_session.uuid}")
        self.assertEqual(SurveyResponse.objects.filter(campaign=campaign).count(), 2)

    def test_every_live_call_ended_campaign_is_offered(self):
        """The admin panel offers this trigger to any campaign, so any campaign must get it."""
        _campaign(
            slug=surveys.POST_CALL_SLUG,
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        # User-scoped: asked once ever rather than once per call, and no context to key on.
        second = _campaign(
            slug="call-followup",
            name="Call follow-up",
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
        )

        surveys.offer_post_call_survey(self.user, _finished_session(self.user, self.partner))

        self.assertEqual(SurveyResponse.objects.filter(campaign=second).count(), 1)
        self.assertEqual(SurveyResponse.objects.filter(campaign=second).first().context_key, "")

    def test_post_call_survey_skips_random_call_sessions(self):
        _campaign(
            slug=surveys.POST_CALL_SLUG,
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        session = _finished_session(self.user, self.partner)
        LivekitSession.objects.filter(pk=session.pk).update(random_call_session=True)
        session.refresh_from_db()

        self.assertIsNone(surveys.offer_post_call_survey(self.user, session))
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_post_call_survey_skips_calls_of_ten_minutes_or_more(self):
        _campaign(
            slug=surveys.POST_CALL_SLUG,
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        session = _finished_session(self.user, self.partner, minutes=10)

        self.assertIsNone(surveys.offer_post_call_survey(self.user, session))
        self.assertEqual(SurveyResponse.objects.count(), 0)

    def test_context_scoped_campaign_refuses_an_empty_context_key(self):
        campaign = _campaign(
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        with self.assertRaises(ValueError):
            surveys.offer_survey(campaign, self.user)


class PendingSurveyTests(TestCase):
    def setUp(self):
        self.user = register_user()
        self.partner = register_user()

    def test_inactive_campaign_offers_nothing(self):
        _campaign(active=False)
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

    def test_campaign_outside_its_window_offers_nothing(self):
        _campaign(starts_at=timezone.now() + timedelta(days=1))
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

        SurveyCampaign.objects.update(starts_at=None, ends_at=timezone.now() - timedelta(days=1))
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

    def test_eligible_user_gets_an_offer_row(self):
        campaign = _campaign()
        pending = surveys.pending_survey_for_user(self.user)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.campaign_id, campaign.pk)
        self.assertEqual(pending.status, SurveyResponse.Status.SHOWN)

    def test_offer_is_not_repeated_within_the_cooldown(self):
        _campaign()
        pending = surveys.pending_survey_for_user(self.user)
        pending.mark_shown()
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

    def test_offer_returns_after_the_cooldown(self):
        _campaign()
        pending = surveys.pending_survey_for_user(self.user)
        pending.mark_shown()
        SurveyResponse.objects.filter(pk=pending.pk).update(
            shown_at=timezone.now() - surveys.SHOW_COOLDOWN - timedelta(minutes=1)
        )
        self.assertIsNotNone(surveys.pending_survey_for_user(self.user))

    def test_offer_expires_after_max_shows(self):
        _campaign(max_shows=1)
        pending = surveys.pending_survey_for_user(self.user)
        pending.mark_shown()
        SurveyResponse.objects.filter(pk=pending.pk).update(
            shown_at=timezone.now() - surveys.SHOW_COOLDOWN - timedelta(minutes=1)
        )

        self.assertIsNone(surveys.pending_survey_for_user(self.user))
        pending.refresh_from_db()
        self.assertEqual(pending.status, SurveyResponse.Status.EXPIRED)

    def test_context_scoped_campaign_is_skipped_not_raised(self):
        """A row written around the model must not take delivery down for everyone."""
        campaign = _campaign(
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        SurveyCampaign.objects.filter(pk=campaign.pk).update(trigger=SurveyCampaign.Trigger.ON_SESSION)

        self.assertIsNone(surveys.pending_survey_for_user(self.user))

    def test_a_second_campaign_waits_for_the_cooldown(self):
        """One card per quiet period, whichever campaign it belongs to.

        The client refetches as soon as a survey closes, so without a user-wide rule
        answering one survey hands over the next one immediately.
        """
        _campaign(slug="first-campaign", name="First")
        _campaign(slug="second-campaign", name="Second")

        pending = surveys.pending_survey_for_user(self.user)
        pending.mark_shown()
        surveys.submit_survey(pending, {"rating": 5})
        # Campaigns are ordered newest first, so which one wins is not the point here —
        # the point is that the other one waits.
        delivered_first = pending.campaign_id

        self.assertIsNone(surveys.pending_survey_for_user(self.user))

        SurveyResponse.objects.filter(pk=pending.pk).update(
            shown_at=timezone.now() - surveys.SHOW_COOLDOWN - timedelta(minutes=1)
        )
        later = surveys.pending_survey_for_user(self.user)
        self.assertIsNotNone(later)
        self.assertNotEqual(later.campaign_id, delivered_first)

    def test_cooldown_defers_an_event_offer_without_losing_it(self):
        """A post-call offer inside the quiet period is held, not dropped."""
        session_campaign = _campaign(slug="session-campaign")
        post_call = _campaign(
            slug=surveys.POST_CALL_SLUG,
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        shown = surveys.pending_survey_for_user(self.user)
        shown.mark_shown()
        self.assertEqual(shown.campaign_id, session_campaign.pk)

        offer = surveys.offer_post_call_survey(self.user, _finished_session(self.user, self.partner))
        self.assertIsNotNone(offer)
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

        SurveyResponse.objects.filter(pk=shown.pk).update(
            shown_at=timezone.now() - surveys.SHOW_COOLDOWN - timedelta(minutes=1)
        )
        later = surveys.pending_survey_for_user(self.user)
        self.assertEqual(later.pk, offer.pk)
        self.assertEqual(later.campaign_id, post_call.pk)

    def test_an_offer_never_rendered_does_not_start_the_cooldown(self):
        """shown_at is written by the client confirming it painted the card, not by the offer."""
        _campaign(slug="first-campaign", name="First")
        _campaign(slug="second-campaign", name="Second")

        self.assertIsNotNone(surveys.pending_survey_for_user(self.user))
        # No mark_shown: the modal never opened, so nothing was shown and nothing is blocked.
        self.assertIsNotNone(surveys.pending_survey_for_user(self.user))

    def test_event_offers_are_delivered_before_session_campaigns(self):
        session_campaign = _campaign(slug="session-campaign")
        post_call = _campaign(
            slug=surveys.POST_CALL_SLUG,
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )
        surveys.offer_post_call_survey(self.user, _finished_session(self.user, self.partner))

        pending = surveys.pending_survey_for_user(self.user)
        self.assertEqual(pending.campaign_id, post_call.pk)
        self.assertFalse(SurveyResponse.objects.filter(campaign=session_campaign).exists())


class SurveyAnswerValidationTests(TestCase):
    def setUp(self):
        self.user = register_user()
        self.campaign = _campaign(
            questions=[
                _q("rating", "rating", required=True),
                _q("comment", "text"),
                _q("reason", "choice", options=[_choice("price"), _choice("people")]),
            ]
        )
        self.response = surveys.offer_survey(self.campaign, self.user)

    def test_required_answer_is_enforced(self):
        with self.assertRaises(ValidationError):
            surveys.submit_survey(self.response, {"comment": "nice"})

    def test_rating_must_be_inside_the_scale(self):
        with self.assertRaises(ValidationError):
            surveys.submit_survey(self.response, {"rating": 6})

    def test_choice_must_be_a_declared_option(self):
        with self.assertRaises(ValidationError):
            surveys.submit_survey(self.response, {"rating": 4, "reason": "weather"})

    def test_unknown_keys_are_rejected(self):
        with self.assertRaises(ValidationError):
            surveys.submit_survey(self.response, {"rating": 4, "sneaky": "value"})

    def test_blank_optional_answers_are_dropped(self):
        surveys.submit_survey(self.response, {"rating": 4, "comment": "   "})
        self.response.refresh_from_db()
        self.assertEqual(self.response.answers, {"rating": 4})

    def test_rating_is_mirrored_onto_the_column(self):
        surveys.submit_survey(self.response, {"rating": 5, "comment": "great"})
        self.response.refresh_from_db()
        self.assertEqual(self.response.rating, 5)
        self.assertEqual(self.response.status, SurveyResponse.Status.SUBMITTED)
        self.assertIsNotNone(self.response.submitted_at)

    def test_cannot_submit_twice(self):
        surveys.submit_survey(self.response, {"rating": 5})
        with self.assertRaises(ValidationError):
            surveys.submit_survey(self.response, {"rating": 1})


class LegacyPostCallReviewTests(TestCase):
    """``POST /api/livekit/review`` for clients that predate the survey endpoints."""

    def setUp(self):
        self.user = register_user()
        self.partner = register_user()
        self.campaign = _campaign(
            slug=surveys.POST_CALL_SLUG,
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
        )

    def _submit(self, **kwargs):
        params = {"live_session": None, "rating": 4, "review": "fine", "response_id": None}
        params.update(kwargs)
        return surveys.submit_post_call_review(self.user, **params)

    def test_review_id_cannot_reach_another_campaign(self):
        # review_id is client-supplied and used to be a PostCallReview pk, so an id landing
        # on another campaign's row is stale or crafted — either way it is not a target.
        other = _campaign(slug="other-campaign", name="Other campaign")
        offer = surveys.offer_survey(other, self.user)
        session = _finished_session(self.user, self.partner)

        response = self._submit(live_session=session, response_id=offer.pk)

        self.assertEqual(response.campaign_id, self.campaign.pk)
        offer.refresh_from_db()
        self.assertEqual(offer.answers, {})
        self.assertEqual(offer.status, SurveyResponse.Status.SHOWN)

    def test_stale_review_id_falls_back_to_the_session(self):
        session = _finished_session(self.user, self.partner)
        offer = surveys.offer_post_call_survey(self.user, session)

        response = self._submit(live_session=session, response_id=offer.pk + 10_000)

        self.assertEqual(response.pk, offer.pk)
        self.assertEqual(response.rating, 4)

    def test_own_review_is_still_editable(self):
        session = _finished_session(self.user, self.partner)
        first = self._submit(live_session=session)
        second = self._submit(live_session=session, rating=1, review="actually poor", response_id=first.pk)

        self.assertEqual(first.pk, second.pk)
        second.refresh_from_db()
        self.assertEqual(second.rating, 1)
        self.assertEqual(second.answers["comment"], "actually poor")

    def test_review_without_a_session_is_still_recorded(self):
        # The old endpoint always stored the review, session or not. Each one gets its own
        # context key so the uniqueness rule does not silently drop the second.
        first = self._submit()
        second = self._submit(rating=2, review="second thought")

        self.assertNotEqual(first.pk, second.pk)
        self.assertTrue(first.context_key.startswith("legacy:"))
        self.assertEqual(
            SurveyResponse.objects.filter(campaign=self.campaign, status=SurveyResponse.Status.SUBMITTED).count(), 2
        )

    def test_retired_campaign_takes_no_new_reviews(self):
        SurveyCampaign.objects.filter(pk=self.campaign.pk).update(active=False)
        with self.assertRaises(ValidationError):
            self._submit(live_session=_finished_session(self.user, self.partner))

    def test_retired_campaign_still_accepts_an_open_offer(self):
        session = _finished_session(self.user, self.partner)
        offer = surveys.offer_post_call_survey(self.user, session)
        SurveyCampaign.objects.filter(pk=self.campaign.pk).update(active=False)

        response = self._submit(live_session=session)

        self.assertEqual(response.pk, offer.pk)
        self.assertEqual(response.status, SurveyResponse.Status.SUBMITTED)


class AdminSurveyApiTests(TestCase):
    """The admin panel is now the only way campaigns are created, so these endpoints are the
    real entry point for the feature."""

    ENDPOINT = "/api/admin/survey_campaigns/"

    def setUp(self):
        self.staff = register_user()
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.client.force_login(self.staff)

    def _payload(self, **overrides):
        payload = {
            "slug": "acme-checkin",
            "name": "Acme check-in",
            "copy": {
                "title": localized(de="Wie läuft es?"),
                "description": localized(),
                "submit_button": localized(de="Absenden"),
            },
            "scale": 5,
            "questions": [
                {"id": "rating", "type": "rating", "required": True, "label": localized(de="Bewertung")},
            ],
            "audience_type": "company",
            "audience_value": "acme",
            "eligible_after_event": "",
            "eligible_after_since": None,
            "trigger": "on_session",
            "repeat_scope": "user",
            "context_type": "",
            "active": True,
            "starts_at": None,
            "ends_at": None,
            "max_shows": 3,
        }
        payload.update(overrides)
        return payload

    def _post(self, payload):
        return self.client.post(self.ENDPOINT, data=payload, content_type="application/json")

    def test_requires_staff(self):
        self.client.force_login(register_user())
        self.assertEqual(self.client.get(self.ENDPOINT).status_code, 403)

    def test_creates_a_campaign_with_copy(self):
        response = self._post(self._payload())
        self.assertEqual(response.status_code, 201)
        campaign = SurveyCampaign.objects.get(slug="acme-checkin")
        self.assertEqual(campaign.card_for("de")["title"], "Wie läuft es?")
        # No English was supplied, so English readers get the German.
        self.assertEqual(campaign.card_for("en")["title"], "Wie läuft es?")

    def test_activation_without_copy_is_rejected(self):
        payload = self._payload(copy={"title": localized(), "submit_button": localized()})
        response = self._post(payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("copy", response.json()["errors"])
        self.assertFalse(SurveyCampaign.objects.filter(slug="acme-checkin").exists())

    def test_draft_without_copy_is_allowed(self):
        payload = self._payload(
            active=False,
            copy={"title": localized(), "submit_button": localized()},
        )
        response = self._post(payload)
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["missing_copy"])

    def test_list_reports_delivery(self):
        campaign = _campaign()
        user = register_user()
        offer = surveys.offer_survey(campaign, user)
        offer.mark_shown()
        surveys.submit_survey(offer, {"rating": 5})

        row = next(item for item in self.client.get(self.ENDPOINT).json() if item["slug"] == campaign.slug)
        self.assertEqual((row["offered"], row["rendered"], row["answered"]), (1, 1, 1))
        self.assertEqual(row["mean_rating"], 5.0)

    def test_answered_questions_are_reported_as_locked(self):
        campaign = _campaign()
        SurveyResponse.objects.create(campaign=campaign, user=register_user(), answers={"comment": "hi"})
        detail = self.client.get(f"{self.ENDPOINT}{campaign.pk}/").json()
        self.assertEqual(detail["locked_questions"], ["comment"])

    def test_campaign_with_responses_cannot_be_deleted(self):
        campaign = _campaign()
        SurveyResponse.objects.create(campaign=campaign, user=register_user(), answers={})
        response = self.client.delete(f"{self.ENDPOINT}{campaign.pk}/")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(SurveyCampaign.objects.filter(pk=campaign.pk).exists())

    def test_unused_campaign_can_be_deleted(self):
        campaign = _campaign()
        self.assertEqual(self.client.delete(f"{self.ENDPOINT}{campaign.pk}/").status_code, 204)
        self.assertFalse(SurveyCampaign.objects.filter(pk=campaign.pk).exists())

    def test_options_lists_companies_and_filters(self):
        self.staff.state.company = "lingoda"
        self.staff.state.save()
        payload = self.client.get(f"{self.ENDPOINT}options/").json()
        self.assertIn("lingoda", payload["companies"])
        values = [item["value"] for item in payload["filters"]]
        self.assertIn("volunteers", values)
        self.assertNotIn("capegemini", values)
        self.assertNotIn("none", values)

    def test_detail_reports_scale_locked_after_a_rating(self):
        campaign = _campaign()
        detail = self.client.get(f"{self.ENDPOINT}{campaign.pk}/").json()
        self.assertFalse(detail["scale_locked"])
        SurveyResponse.objects.create(campaign=campaign, user=register_user(), answers={"rating": 5}, rating=5)
        detail = self.client.get(f"{self.ENDPOINT}{campaign.pk}/").json()
        self.assertTrue(detail["scale_locked"])


class AdminSurveyResponseApiTests(TestCase):
    ENDPOINT = "/api/admin/survey_responses/"

    def setUp(self):
        self.staff = register_user()
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
        self.client.force_login(self.staff)
        self.campaign = _campaign()
        self.other = _campaign(slug="other-campaign", name="Other campaign")
        self.user = register_user()
        self.offer = surveys.offer_survey(self.campaign, self.user)
        self.offer.mark_shown()
        surveys.submit_survey(self.offer, {"rating": 4, "comment": "great call"})
        surveys.offer_survey(self.other, self.user)

    def test_requires_staff(self):
        self.client.force_login(register_user())
        self.assertEqual(self.client.get(self.ENDPOINT).status_code, 403)

    def test_lists_responses_with_comment_and_options(self):
        payload = self.client.get(self.ENDPOINT).json()
        self.assertEqual(payload["results_total"], 2)
        submitted = next(row for row in payload["results"] if row["status"] == "submitted")
        self.assertEqual(submitted["campaign_name"], "Test campaign")
        self.assertEqual(submitted["user_email"], self.user.email)
        self.assertEqual(submitted["rating"], 4)
        self.assertEqual(submitted["comment"], "great call")
        self.assertEqual(submitted["shown_count"], 1)
        campaign_ids = {option["value"] for option in payload["campaign_options"]}
        self.assertIn(str(self.campaign.pk), campaign_ids)
        self.assertIn(str(self.other.pk), campaign_ids)
        statuses = {option["value"] for option in payload["status_options"]}
        self.assertEqual(statuses, {"shown", "submitted", "dismissed", "expired"})

    def test_filters_by_campaign(self):
        payload = self.client.get(self.ENDPOINT, {"campaign": self.campaign.pk}).json()
        self.assertEqual(payload["results_total"], 1)
        self.assertEqual(payload["results"][0]["campaign_id"], self.campaign.pk)
        self.assertEqual(payload["results"][0]["status"], "submitted")

    def test_filters_by_status(self):
        payload = self.client.get(self.ENDPOINT, {"status": "shown"}).json()
        self.assertEqual(payload["results_total"], 1)
        self.assertEqual(payload["results"][0]["campaign_id"], self.other.pk)

    def test_searches_by_email(self):
        payload = self.client.get(self.ENDPOINT, {"search": self.user.email.split("@")[0]}).json()
        self.assertEqual(payload["results_total"], 2)
        empty = self.client.get(self.ENDPOINT, {"search": "nobody-no-match"}).json()
        self.assertEqual(empty["results_total"], 0)


class SurveyApiTests(TestCase):
    def setUp(self):
        self.user = register_user()
        self.other_user = register_user()
        self.campaign = _campaign()
        self.client.force_login(self.user)

    def test_pending_returns_null_without_a_campaign(self):
        SurveyCampaign.objects.update(active=False)
        response = self.client.get("/api/surveys/pending")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["survey"])

    def test_pending_describes_the_card(self):
        response = self.client.get("/api/surveys/pending")
        payload = response.json()["survey"]
        self.assertEqual(payload["campaign"], self.campaign.slug)
        # Copy arrives as finished text, so the client has no language decision to make.
        self.assertEqual(payload["title"], "Wie gefällt es dir?")
        self.assertEqual(payload["submit_button"], "Absenden")
        self.assertEqual(payload["scale"], 5)
        self.assertNotIn("rating_labels", payload)
        self.assertEqual([q["id"] for q in payload["questions"]], ["rating", "comment"])

    def test_shown_records_delivery(self):
        survey_id = self.client.get("/api/surveys/pending").json()["survey"]["id"]
        response = self.client.post(f"/api/surveys/{survey_id}/shown")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SurveyResponse.objects.get(pk=survey_id).shown_count, 1)

    def test_submit_stores_the_answers(self):
        survey_id = self.client.get("/api/surveys/pending").json()["survey"]["id"]
        response = self.client.post(
            f"/api/surveys/{survey_id}/submit",
            data={"answers": {"rating": 4, "comment": "good"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        stored = SurveyResponse.objects.get(pk=survey_id)
        self.assertEqual(stored.answers, {"rating": 4, "comment": "good"})
        self.assertEqual(stored.rating, 4)

    def test_submit_rejects_invalid_answers(self):
        survey_id = self.client.get("/api/surveys/pending").json()["survey"]["id"]
        response = self.client.post(
            f"/api/surveys/{survey_id}/submit",
            data={"answers": {"comment": "no rating"}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)

    def test_dismiss_is_recorded(self):
        survey_id = self.client.get("/api/surveys/pending").json()["survey"]["id"]
        self.assertEqual(self.client.post(f"/api/surveys/{survey_id}/dismiss").status_code, 200)
        self.assertEqual(SurveyResponse.objects.get(pk=survey_id).status, SurveyResponse.Status.DISMISSED)

    def test_cannot_answer_someone_elses_survey(self):
        foreign = surveys.offer_survey(self.campaign, self.other_user)
        response = self.client.post(
            f"/api/surveys/{foreign.pk}/submit",
            data={"answers": {"rating": 1}},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_pending_requires_authentication(self):
        self.client.logout()
        self.assertIn(self.client.get("/api/surveys/pending").status_code, (401, 403))


class DeletedUserFreeTextTests(TestCase):
    def test_free_text_is_scrubbed_and_ratings_are_kept(self):
        from management.tasks import _scrub_survey_free_text

        user = register_user()
        campaign = _campaign()
        response = SurveyResponse.objects.create(
            campaign=campaign,
            user=user,
            answers={"rating": 5, "comment": "I work at Acme with Jane"},
            rating=5,
            status=SurveyResponse.Status.SUBMITTED,
        )

        _scrub_survey_free_text(user)
        response.refresh_from_db()
        self.assertEqual(response.answers, {"rating": 5})
        self.assertEqual(response.rating, 5)
