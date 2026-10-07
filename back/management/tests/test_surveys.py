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

    def test_deduplicates_question_ids_keeping_the_first(self):
        campaign = _campaign(questions=[_q("rating", "rating", required=True), _q("rating", "text")])
        ids = [question["id"] for question in campaign.questions]
        self.assertEqual(ids[0], "rating")
        self.assertNotEqual(ids[1], "rating")
        self.assertRegex(ids[1], r"^q_[0-9a-f]{12}$")

    def test_assigns_ids_when_missing_or_invalid(self):
        missing = _q("comment", "text")
        missing.pop("id")
        invalid = _q("other", "text")
        invalid["id"] = "Not Valid!"
        campaign = _campaign(questions=[missing, invalid])
        ids = [question["id"] for question in campaign.questions]
        self.assertEqual(len(set(ids)), 2)
        for qid in ids:
            self.assertRegex(qid, r"^q_[0-9a-f]{12}$")

    def test_keeps_valid_question_ids(self):
        campaign = _campaign()
        self.assertEqual([question["id"] for question in campaign.questions], ["rating", "comment"])

    def test_rejects_choice_question_without_options(self):
        with self.assertRaises(ValidationError):
            _campaign(questions=[{"id": "reason", "type": "choice"}])

    def test_rejects_multiselect_question_without_options(self):
        with self.assertRaises(ValidationError):
            _campaign(questions=[{"id": "topics", "type": "multiselect"}])

    def test_allows_multiple_ratings_with_their_own_scale(self):
        campaign = _campaign(
            scale=5,
            questions=[
                _q("ease", "rating", required=True, scale=10),
                _q("nps", "rating", required=False, scale=5),
            ],
        )
        card = campaign.card_for("de")
        self.assertEqual(card["questions"][0]["scale"], 10)
        self.assertEqual(card["questions"][1]["scale"], 5)

    def test_rating_question_is_optional(self):
        campaign = _campaign(questions=[_q("comment", "text", required=True)])
        self.assertTrue(campaign.active)

    def test_rejects_an_empty_question_list(self):
        with self.assertRaises(ValidationError):
            _campaign(questions=[])

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

    def test_link_delivery_rejects_match_scoped_campaigns(self):
        with self.assertRaises(ValidationError):
            _campaign(
                trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
                repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
                context_type=SurveyCampaign.ContextType.MATCH,
                available_via_link=True,
            )

    def test_no_in_app_trigger_requires_link_delivery(self):
        with self.assertRaises(ValidationError):
            _campaign(trigger=SurveyCampaign.Trigger.NONE, available_via_link=False)

    def test_no_in_app_trigger_is_allowed_with_link_delivery(self):
        campaign = _campaign(trigger=SurveyCampaign.Trigger.NONE, available_via_link=True)
        self.assertEqual(campaign.trigger, SurveyCampaign.Trigger.NONE)

    def test_link_delivery_allows_live_session_scoped_campaigns(self):
        campaign = _campaign(
            trigger=SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
            repeat_scope=SurveyCampaign.RepeatScope.CONTEXT,
            context_type=SurveyCampaign.ContextType.LIVE_SESSION,
            available_via_link=True,
        )
        self.assertTrue(campaign.available_via_link)

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

    def test_cannot_change_an_answered_rating_question_scale(self):
        self.campaign.questions = [
            _q("rating", "rating", required=True, scale=5),
            _q("comment", "text"),
        ]
        with self.assertRaises(ValidationError):
            self.campaign.questions = [
                _q("rating", "rating", required=True, scale=10),
                _q("comment", "text"),
            ]
            self.campaign.save()

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

    def test_new_rating_above_an_answered_one_can_use_another_scale(self):
        self.campaign.questions = [
            _q("ease", "rating", scale=10),
            _q("rating", "rating", required=True, scale=5),
            _q("comment", "text"),
        ]
        self.campaign.save()
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.scale, 5)


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

    def test_filter_audience_uses_the_shared_audience_filters(self):
        campaign = _campaign(
            audience_type=SurveyCampaign.AudienceType.FILTER,
            audience_value="volunteers",
        )
        self.assertFalse(surveys.user_matches_audience(campaign, self.user))
        volunteer = register_user()
        volunteer.profile.user_type = "volunteer"
        volunteer.profile.save()
        self.assertTrue(surveys.user_matches_audience(campaign, volunteer))

    def test_onboarded_learner_audience_requires_onboarding(self):
        campaign = _campaign(
            audience_type=SurveyCampaign.AudienceType.FILTER,
            audience_value="onboarded_learners",
        )
        self.assertFalse(surveys.user_matches_audience(campaign, self.user))

        self.user.state.is_onboarded = True
        self.user.state.save(update_fields=["is_onboarded"])
        self.assertTrue(surveys.user_matches_audience(campaign, self.user))

    def test_audience_picker_uses_shared_filter_labels(self):
        choices = {choice["value"]: choice["label"] for choice in surveys.audience_filter_choices()}

        self.assertEqual(choices["learners"], "All registered learners")
        self.assertEqual(choices["volunteers"], "All registered volunteers")
        self.assertEqual(choices["onboarded_learners"], "Onboarded learners")
        self.assertEqual(choices["onboarded_volunteers"], "Onboarded volunteers")

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

    def test_halfway_match_success_uses_half_the_live_token_threshold(self):
        from django.db.models import Q

        from management.match_success import halfway_token_threshold, tokens_from_total_minutes
        from management.match_success.versions.v1_total_minutes import MINUTE_TOKEN_THRESHOLDS
        from management.models.matches import Match

        Match.objects.filter(Q(user1=self.user) | Q(user2=self.user)).delete()
        campaign = _campaign(eligible_after_event=SurveyCampaign.EligibleAfterEvent.HALFWAY_MATCH_SUCCESS)
        tandem = register_user()
        Match.objects.filter(Q(user1=tandem) | Q(user2=tandem)).delete()
        match = Match.objects.create(user1=self.user, user2=tandem)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        half = halfway_token_threshold()
        minutes_at_half = next(minutes for minutes, tokens in MINUTE_TOKEN_THRESHOLDS if tokens >= half)
        minutes_below = next(minutes for minutes, tokens in reversed(MINUTE_TOKEN_THRESHOLDS) if tokens < half)

        below = _finished_session(self.user, tandem, minutes=int(minutes_below))
        Match.objects.filter(pk=match.pk).update(created_at=below.created_at - timedelta(seconds=1))
        self.assertLess(tokens_from_total_minutes(minutes_below), half)
        self.assertFalse(surveys.user_is_eligible(campaign, self.user))

        below.delete()
        at_half = _finished_session(self.user, tandem, minutes=int(minutes_at_half))
        Match.objects.filter(pk=match.pk).update(created_at=at_half.created_at - timedelta(seconds=1))
        self.assertGreaterEqual(tokens_from_total_minutes(minutes_at_half), half)
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

    def test_halfway_match_success_counts_off_platform_completion(self):
        from django.db.models import Q

        from management.models.matches import Match

        Match.objects.filter(Q(user1=self.user) | Q(user2=self.user)).delete()
        campaign = _campaign(eligible_after_event=SurveyCampaign.EligibleAfterEvent.HALFWAY_MATCH_SUCCESS)
        tandem = register_user()
        Match.objects.filter(Q(user1=tandem) | Q(user2=tandem)).delete()
        Match.objects.create(user1=self.user, user2=tandem, completed_off_plattform=True)
        self.assertTrue(surveys.user_is_eligible(campaign, self.user))

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

    def test_no_in_app_trigger_is_not_offered_as_a_popup(self):
        _campaign(trigger=SurveyCampaign.Trigger.NONE, available_via_link=True)
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

    def test_switching_to_no_in_app_trigger_stops_open_offers(self):
        campaign = _campaign()
        self.assertIsNotNone(surveys.pending_survey_for_user(self.user))
        _campaign(trigger=SurveyCampaign.Trigger.NONE, available_via_link=True)
        self.assertIsNone(surveys.pending_survey_for_user(self.user))
        self.assertEqual(SurveyResponse.objects.get(campaign=campaign).status, SurveyResponse.Status.SHOWN)

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

    def test_submit_stores_answers_and_marks_submitted(self):
        surveys.submit_survey(self.response, {"rating": 5, "comment": "great"})
        self.response.refresh_from_db()
        self.assertEqual(self.response.answers, {"rating": 5, "comment": "great"})
        self.assertEqual(self.response.status, SurveyResponse.Status.SUBMITTED)
        self.assertIsNotNone(self.response.submitted_at)

    def test_cannot_submit_twice(self):
        surveys.submit_survey(self.response, {"rating": 5})
        with self.assertRaises(ValidationError):
            surveys.submit_survey(self.response, {"rating": 1})

    def test_text_only_survey_can_be_submitted_without_a_rating(self):
        campaign = _campaign(slug="text-only", questions=[_q("comment", "text", required=True)])
        response = surveys.offer_survey(campaign, self.user)
        surveys.submit_survey(response, {"comment": "just text"})
        response.refresh_from_db()
        self.assertEqual(response.answers, {"comment": "just text"})
        self.assertEqual(response.status, SurveyResponse.Status.SUBMITTED)

    def test_rating_uses_the_question_scale_not_the_campaign(self):
        campaign = _campaign(
            slug="wide-scale",
            scale=5,
            questions=[_q("ease", "rating", required=True, scale=10)],
        )
        response = surveys.offer_survey(campaign, self.user)
        surveys.submit_survey(response, {"ease": 9})
        response.refresh_from_db()
        self.assertEqual(response.answers, {"ease": 9})

    def test_multiselect_is_stored_in_option_order(self):
        campaign = _campaign(
            slug="multi",
            questions=[
                _q(
                    "topics",
                    "multiselect",
                    required=True,
                    options=[_choice("chat"), _choice("calls"), _choice("events")],
                )
            ],
        )
        response = surveys.offer_survey(campaign, self.user)
        surveys.submit_survey(response, {"topics": ["events", "chat", "events"]})
        response.refresh_from_db()
        self.assertEqual(response.answers, {"topics": ["chat", "events"]})

    def test_multiselect_rejects_unknown_options(self):
        campaign = _campaign(
            slug="multi-bad",
            questions=[_q("topics", "multiselect", required=True, options=[_choice("chat")])],
        )
        response = surveys.offer_survey(campaign, self.user)
        with self.assertRaises(ValidationError):
            surveys.submit_survey(response, {"topics": ["weather"]})

    def test_required_multiselect_needs_at_least_one(self):
        campaign = _campaign(
            slug="multi-required",
            questions=[_q("topics", "multiselect", required=True, options=[_choice("chat")])],
        )
        response = surveys.offer_survey(campaign, self.user)
        with self.assertRaises(ValidationError):
            surveys.submit_survey(response, {"topics": []})


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

    def test_creates_mixed_question_types(self):
        response = self._post(
            self._payload(
                questions=[
                    {
                        "id": "ease",
                        "type": "rating",
                        "required": True,
                        "scale": 10,
                        "label": localized(de="Einfachheit"),
                    },
                    {
                        "id": "reason",
                        "type": "choice",
                        "required": True,
                        "label": localized(de="Grund"),
                        "options": [{"value": "price", "label": localized(de="Preis")}],
                    },
                    {
                        "id": "topics",
                        "type": "multiselect",
                        "required": False,
                        "label": localized(de="Themen"),
                        "options": [
                            {"value": "chat", "label": localized(de="Chat")},
                            {"value": "calls", "label": localized(de="Calls")},
                        ],
                    },
                ]
            )
        )
        self.assertEqual(response.status_code, 201)
        questions = response.json()["questions"]
        self.assertEqual([question["type"] for question in questions], ["rating", "choice", "multiselect"])
        self.assertEqual(questions[0]["scale"], 10)
        self.assertEqual(response.json()["scale"], 5)

    def test_creates_a_campaign_without_a_rating(self):
        response = self._post(
            self._payload(
                questions=[
                    {"id": "comment", "type": "text", "required": True, "label": localized(de="Kommentar")},
                ]
            )
        )
        self.assertEqual(response.status_code, 201)
        types = [question["type"] for question in response.json()["questions"]]
        self.assertEqual(types, ["text"])

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
        self.assertNotIn("mean_rating", row)

    def test_link_opened_response_counts_as_rendered(self):
        campaign = _link_campaign()
        user = register_user()
        state, response = surveys.survey_for_link(user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.AVAILABLE)
        self.assertEqual(response.shown_count, 0)
        self.assertIsNotNone(response.opened_at)

        row = next(item for item in self.client.get(self.ENDPOINT).json() if item["slug"] == campaign.slug)
        self.assertEqual(row["rendered"], 1)
        self.assertEqual(row["offered"], 1)

    def test_creates_a_link_only_campaign(self):
        response = self._post(
            self._payload(trigger="none", available_via_link=True, audience_type="all", audience_value="")
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["available_via_link"])
        self.assertEqual(response.json()["trigger"], "none")

    def test_no_in_app_trigger_without_link_is_rejected(self):
        response = self._post(self._payload(trigger="none", available_via_link=False))
        self.assertEqual(response.status_code, 400)

    def test_link_delivery_on_match_scoped_campaign_is_rejected(self):
        response = self._post(
            self._payload(
                trigger="event:call_ended",
                repeat_scope="context",
                context_type="match",
                available_via_link=True,
            )
        )
        self.assertEqual(response.status_code, 400)

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

    def test_options_serves_the_trigger_and_eligibility_enums(self):
        """The form's dropdowns are served, not restated in the frontend.

        They were duplicated once and drifted: a whole trigger was missing from the admin
        panel, so a campaign type the backend supported could not be created.
        """
        payload = self.client.get(f"{self.ENDPOINT}options/").json()

        for key, choices in (
            ("triggers", SurveyCampaign.Trigger.choices),
            ("eligible_after_events", SurveyCampaign.EligibleAfterEvent.choices),
        ):
            served = [(option["value"], option["label"]) for option in payload[key]]
            self.assertEqual(served, [(value, str(label)) for value, label in choices])

    def test_options_lists_companies_and_filters(self):
        self.staff.state.company = "lingoda"
        self.staff.state.save()
        payload = self.client.get(f"{self.ENDPOINT}options/").json()
        self.assertIn("lingoda", payload["companies"])
        values = [item["value"] for item in payload["filters"]]
        self.assertIn("volunteers", values)
        self.assertNotIn("capegemini", values)
        self.assertNotIn("none", values)

    def test_detail_reports_answered_questions_as_locked(self):
        campaign = _campaign()
        detail = self.client.get(f"{self.ENDPOINT}{campaign.pk}/").json()
        self.assertEqual(detail["locked_questions"], [])
        SurveyResponse.objects.create(campaign=campaign, user=register_user(), answers={"rating": 5})
        detail = self.client.get(f"{self.ENDPOINT}{campaign.pk}/").json()
        self.assertEqual(detail["locked_questions"], ["rating"])


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

    def test_lists_responses_with_answers_and_delivery(self):
        payload = self.client.get(self.ENDPOINT).json()
        self.assertEqual(payload["results_total"], 2)
        self.assertIsNone(payload["summary"])
        submitted = next(row for row in payload["results"] if row["status"] == "submitted")
        self.assertEqual(submitted["campaign_name"], "Test campaign")
        self.assertEqual(submitted["user_email"], self.user.email)
        self.assertEqual(submitted["answers"], {"rating": 4, "comment": "great call"})
        self.assertEqual(submitted["delivery_channel"], SurveyResponse.DeliveryChannel.PENDING)
        self.assertEqual(submitted["shown_count"], 1)
        self.assertEqual([question["id"] for question in submitted["questions"]], ["rating", "comment"])
        self.assertNotIn("comment", submitted)
        self.assertNotIn("rating", submitted)
        campaign_ids = {option["value"] for option in payload["campaign_options"]}
        self.assertIn(str(self.campaign.pk), campaign_ids)
        self.assertIn(str(self.other.pk), campaign_ids)
        statuses = {option["value"] for option in payload["status_options"]}
        self.assertEqual(statuses, {"shown", "submitted", "dismissed", "expired"})

    def test_rating_questions_carry_the_campaign_fallback_scale(self):
        SurveyCampaign.objects.filter(pk=self.campaign.pk).update(scale=10)
        payload = self.client.get(self.ENDPOINT, {"campaign": self.campaign.pk}).json()
        rating = next(q for q in payload["results"][0]["questions"] if q["id"] == "rating")
        self.assertEqual(rating["scale"], 10)

    def test_campaign_filter_includes_rating_summary(self):
        payload = self.client.get(self.ENDPOINT, {"campaign": self.campaign.pk}).json()
        self.assertEqual(payload["results_total"], 1)
        self.assertEqual(
            payload["summary"],
            {
                "offered": 1,
                "answered": 1,
                "rating_means": [
                    {"id": "rating", "label": "Bewertung", "scale": 5, "mean": 4.0, "n": 1},
                ],
            },
        )

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
            status=SurveyResponse.Status.SUBMITTED,
        )

        _scrub_survey_free_text(user)
        response.refresh_from_db()
        self.assertEqual(response.answers, {"rating": 5})


def _link_campaign(**overrides) -> SurveyCampaign:
    return _campaign(available_via_link=True, **overrides)


def _session_scoped_link_campaign(**overrides) -> SurveyCampaign:
    fields = {
        "trigger": SurveyCampaign.Trigger.NON_QUALIFYING_CALL_ENDED,
        "repeat_scope": SurveyCampaign.RepeatScope.CONTEXT,
        "context_type": SurveyCampaign.ContextType.LIVE_SESSION,
        "available_via_link": True,
    }
    fields.update(overrides)
    return _campaign(**fields)


class SurveyLinkTests(TestCase):
    def setUp(self):
        self.user = register_user()
        self.partner = register_user()

    def test_exhausted_popup_offer_is_still_answerable_at_the_link(self):
        campaign = _link_campaign(max_shows=1)
        offer = surveys.offer_survey(campaign, self.user)
        offer.mark_shown()
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.AVAILABLE)
        # The pending poll expires the popup row while the page is open; submit still works.
        SurveyResponse.objects.filter(pk=offer.pk).update(
            shown_at=timezone.now() - surveys.SHOW_COOLDOWN - timedelta(minutes=1)
        )
        self.assertIsNone(surveys.pending_survey_for_user(self.user))
        response.refresh_from_db()
        self.assertEqual(response.status, SurveyResponse.Status.EXPIRED)
        surveys.submit_survey(response, {"rating": 4})
        response.refresh_from_db()
        self.assertEqual(response.status, SurveyResponse.Status.SUBMITTED)

    def test_unknown_slug_is_not_found(self):
        state, response = surveys.survey_for_link(self.user, "does-not-exist")
        self.assertEqual(state, surveys.SurveyLinkState.NOT_FOUND)
        self.assertIsNone(response)

    def test_campaign_without_the_flag_is_not_found(self):
        campaign = _campaign()
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.NOT_FOUND)
        self.assertIsNone(response)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_eligible_user_gets_an_available_card(self):
        campaign = _link_campaign()
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.AVAILABLE)
        self.assertEqual(response.campaign_id, campaign.pk)
        self.assertEqual(response.delivery_channel, SurveyResponse.DeliveryChannel.LINK)
        self.assertEqual(response.shown_count, 0)
        self.assertIsNone(response.shown_at)
        self.assertIsNotNone(response.opened_at)

    def test_ineligible_user_creates_no_row(self):
        campaign = _link_campaign(eligible_after_event=SurveyCampaign.EligibleAfterEvent.ONBOARDED)
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.INELIGIBLE)
        self.assertIsNone(response)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_inactive_campaign_is_inactive(self):
        campaign = _link_campaign(active=False)
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.INACTIVE)
        self.assertIsNone(response)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_submitted_then_link_is_already_submitted(self):
        campaign = _link_campaign()
        offer = surveys.offer_survey(campaign, self.user)
        surveys.submit_survey(offer, {"rating": 5})
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.ALREADY_SUBMITTED)
        self.assertIsNone(response)

    def test_expired_then_link_is_available(self):
        campaign = _link_campaign()
        offer = surveys.offer_survey(campaign, self.user)
        offer.expire()
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.AVAILABLE)
        self.assertEqual(response.pk, offer.pk)

    def test_dismissed_via_popup_then_link_is_available(self):
        campaign = _link_campaign()
        offer = surveys.offer_survey(campaign, self.user)
        surveys.dismiss_survey(offer)
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.AVAILABLE)
        self.assertEqual(response.pk, offer.pk)
        self.assertEqual(response.status, SurveyResponse.Status.DISMISSED)
        self.assertIsNotNone(response.opened_at)

    def test_submit_via_link_on_a_dismissed_row_succeeds(self):
        campaign = _link_campaign()
        offer = surveys.offer_survey(campaign, self.user)
        surveys.dismiss_survey(offer)
        _, response = surveys.survey_for_link(self.user, campaign.slug)
        surveys.submit_survey(response, {"rating": 4})
        response.refresh_from_db()
        self.assertEqual(response.status, SurveyResponse.Status.SUBMITTED)

    def test_link_open_does_not_start_popup_cooldown(self):
        popup = _campaign(slug="popup-campaign", name="Popup")
        link = _link_campaign(slug="link-campaign", name="Link")
        surveys.survey_for_link(self.user, link.slug)
        self.assertIsNone(surveys.last_shown_at(self.user))
        pending = surveys.pending_survey_for_user(self.user)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.campaign_id, popup.pk)

    def test_link_created_offer_does_not_appear_as_a_popup(self):
        campaign = _link_campaign()
        surveys.survey_for_link(self.user, campaign.slug)
        self.assertIsNone(surveys.pending_survey_for_user(self.user))

    def test_opened_at_is_not_rewritten(self):
        campaign = _link_campaign()
        _, first = surveys.survey_for_link(self.user, campaign.slug)
        first_opened = first.opened_at
        _, second = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(second.opened_at, first_opened)

    def test_session_scoped_without_param_is_missing_context(self):
        campaign = _session_scoped_link_campaign()
        state, response = surveys.survey_for_link(self.user, campaign.slug)
        self.assertEqual(state, surveys.SurveyLinkState.MISSING_CONTEXT)
        self.assertIsNone(response)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_own_finished_session_is_available(self):
        campaign = _session_scoped_link_campaign()
        session = _finished_session(self.user, self.partner)
        state, response = surveys.survey_for_link(self.user, campaign.slug, live_session_id=session.uuid)
        self.assertEqual(state, surveys.SurveyLinkState.AVAILABLE)
        self.assertEqual(response.context_key, f"live_session:{session.uuid}")
        self.assertEqual(response.live_session_id, session.pk)

    def test_another_users_session_is_not_found(self):
        campaign = _session_scoped_link_campaign()
        stranger = register_user()
        session = _finished_session(stranger, self.partner)
        state, response = surveys.survey_for_link(self.user, campaign.slug, live_session_id=session.uuid)
        self.assertEqual(state, surveys.SurveyLinkState.NOT_FOUND)
        self.assertIsNone(response)
        self.assertFalse(SurveyResponse.objects.exists())

    def test_nonexistent_session_is_not_found(self):
        from uuid import uuid4

        campaign = _session_scoped_link_campaign()
        state, response = surveys.survey_for_link(self.user, campaign.slug, live_session_id=uuid4())
        self.assertEqual(state, surveys.SurveyLinkState.NOT_FOUND)
        self.assertIsNone(response)

    def test_unfinished_session_is_not_found(self):
        campaign = _session_scoped_link_campaign()
        room = LiveKitRoom.objects.create(u1=self.user, u2=self.partner)
        session = LivekitSession.objects.create(room=room, u1=self.user, u2=self.partner, end_time=None)
        state, response = surveys.survey_for_link(self.user, campaign.slug, live_session_id=session.uuid)
        self.assertEqual(state, surveys.SurveyLinkState.NOT_FOUND)
        self.assertIsNone(response)
        self.assertFalse(SurveyResponse.objects.exists())


class SurveyLinkApiTests(TestCase):
    def setUp(self):
        self.user = register_user()
        self.partner = register_user()
        self.campaign = _link_campaign()
        self.client.force_login(self.user)

    def test_requires_authentication(self):
        self.client.logout()
        self.assertIn(self.client.get(f"/api/surveys/{self.campaign.slug}").status_code, (401, 403))

    def test_returns_the_card(self):
        response = self.client.get(f"/api/surveys/{self.campaign.slug}")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state"], "available")
        self.assertEqual(payload["survey"]["campaign"], self.campaign.slug)
        self.assertEqual(payload["survey"]["title"], "Wie gefällt es dir?")

    def test_unknown_slug_is_404(self):
        response = self.client.get("/api/surveys/does-not-exist")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("state", response.json())

    def test_flag_off_is_404(self):
        hidden = _campaign(slug="hidden-campaign")
        response = self.client.get(f"/api/surveys/{hidden.slug}")
        self.assertEqual(response.status_code, 404)

    def test_ineligible_is_structured_200(self):
        campaign = _link_campaign(
            slug="onboarded-only",
            eligible_after_event=SurveyCampaign.EligibleAfterEvent.ONBOARDED,
        )
        response = self.client.get(f"/api/surveys/{campaign.slug}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"state": "ineligible", "survey": None})

    def test_submit_on_a_dismissed_row_via_the_endpoint(self):
        offer = surveys.offer_survey(self.campaign, self.user)
        surveys.dismiss_survey(offer)
        payload = self.client.get(f"/api/surveys/{self.campaign.slug}").json()
        self.assertEqual(payload["state"], "available")
        self.assertEqual(payload["survey"]["id"], offer.pk)
        submitted = self.client.post(
            f"/api/surveys/{offer.pk}/submit",
            data={"answers": {"rating": 3}},
            content_type="application/json",
        )
        self.assertEqual(submitted.status_code, 200)
        offer.refresh_from_db()
        self.assertEqual(offer.status, SurveyResponse.Status.SUBMITTED)

    def test_foreign_session_is_404(self):
        campaign = _session_scoped_link_campaign(slug="call-survey")
        stranger = register_user()
        session = _finished_session(stranger, self.partner)
        response = self.client.get(f"/api/surveys/{campaign.slug}", {"live_session": str(session.uuid)})
        self.assertEqual(response.status_code, 404)

    def test_own_session_returns_available(self):
        campaign = _session_scoped_link_campaign(slug="call-survey")
        session = _finished_session(self.user, self.partner)
        response = self.client.get(f"/api/surveys/{campaign.slug}", {"live_session": str(session.uuid)})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["state"], "available")
        self.assertEqual(payload["survey"]["context_key"], f"live_session:{session.uuid}")

    def test_match_query_param_is_ignored(self):
        response = self.client.get(f"/api/surveys/{self.campaign.slug}", {"match": "anything"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "available")
