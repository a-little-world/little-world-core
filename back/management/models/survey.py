"""In-app survey campaigns.

A campaign is configuration — audience, active window, cadence, questions and copy — so that
shipping a new survey is a database row rather than new code. Copy lives on the row as
``{"de": ..., "en": ...}``, the same shape as ``QuestionCard.content``. German is required to
go live; English falls back to it.

A response is one row per *offer*, created when the survey is shown rather than when it is
answered. That is deliberate: post-call surveys silently reached nobody between July 2025 and
now because a modal that fails to open produces no error and no row. Offer-time rows plus
``shown_count`` make the same failure visible within days.

Uniqueness is ``(campaign, user, context_key)``. ``context_key`` is empty for once-per-user
surveys and ``live_session:<uuid>`` for once-per-call ones, so both kinds share one table and
one uniqueness rule.
"""

import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: Question ids are effectively a public API for analytics and are immutable once answered,
#: so they are constrained to readable snake_case rather than anything the admin types.
QUESTION_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

MIN_SCALE = 2
MAX_SCALE = 10
MAX_TEXT_ANSWER_LENGTH = 5000

#: Copy lives on the row, per language, the same way ``QuestionCard.content`` does. Campaigns
#: are created in the admin panel by the team running the survey, so the copy has to be
#: editable there: an i18n key would mean a frontend deploy for every new campaign, which
#: defeats the point of a campaign being configuration.
COPY_LANGUAGES = ("de", "en")

#: German is the platform default (``Profile.display_language``) and the only language a
#: campaign must supply. English falls back to it, so a German-only campaign is complete and
#: nobody is forced to write translations they do not need.
PRIMARY_COPY_LANGUAGE = "de"

CAMPAIGN_COPY_FIELDS = ("title", "description", "submit_button")

#: Copy without which the card cannot sensibly render, checked when a campaign goes live.
REQUIRED_CAMPAIGN_COPY_FIELDS = ("title", "submit_button")


def localized(de: str = "", en: str = "") -> dict[str, str]:
    return {"de": de, "en": en}


def default_campaign_copy() -> dict:
    return {field: localized() for field in CAMPAIGN_COPY_FIELDS}


def resolve_localized(value, language: str) -> str:
    """Text for ``language``, falling back to the primary language and then to empty."""
    if not isinstance(value, dict):
        return ""
    return value.get(language) or value.get(PRIMARY_COPY_LANGUAGE) or ""


#: How long a standard call (both people active, not a random call) has to run to count as a
#: real conversation. One threshold, one meaning, used three ways:
#:
#: * at or above it, the call *qualifies* — it triggers the qualifying-call survey, and it
#:   satisfies the ``first_qualifying_call`` journey condition;
#: * below it, the call did not qualify — it triggers the non-qualifying-call survey, which
#:   exists to ask what went wrong.
#:
#: Previously two constants pulled in opposite directions and a user's *longest* calls stopped
#: counting as calls at all. Keep it one number.
QUALIFYING_CALL_MIN_DURATION = timedelta(minutes=10)

#: Whole minutes, for the choice labels below, so they cannot drift from the rule.
_QUALIFYING_MINUTES = int(QUALIFYING_CALL_MIN_DURATION.total_seconds() // 60)


class QuestionType(models.TextChoices):
    RATING = "rating", _("Rating")
    TEXT = "text", _("Text")
    CHOICE = "choice", _("Choice")


def build_context_key(context_type: str, value) -> str:
    """``live_session`` + uuid -> ``"live_session:<uuid>"``. Empty type means user scope."""
    if not context_type:
        return ""
    return f"{context_type}:{value}"


class SurveyCampaign(models.Model):
    class AudienceType(models.TextChoices):
        ALL = "all", _("All users")
        COMPANY = "company", _("Company")
        FILTER = "filter", _("Existing audience filter")

    class Trigger(models.TextChoices):
        ON_SESSION = "on_session", _("Next time the user is in the app")
        #: Value kept as ``event:call_ended``: this is the trigger the existing post-call
        #: campaign already carries, and renaming it would orphan that row.
        NON_QUALIFYING_CALL_ENDED = (
            "event:call_ended",
            _("After a non-qualifying call (under %(minutes)s min; excludes random calls)")
            % {"minutes": _QUALIFYING_MINUTES},
        )
        QUALIFYING_CALL_ENDED = (
            "event:qualifying_call_ended",
            _("After a qualifying call (%(minutes)s min or longer; excludes random calls)")
            % {"minutes": _QUALIFYING_MINUTES},
        )

    class EligibleAfterEvent(models.TextChoices):
        NONE = "", _("Immediately")
        ONBOARDED = "onboarded", _("Onboarded")
        FIRST_QUALIFYING_CALL = (
            "first_qualifying_call",
            _("First qualifying call (%(minutes)s min or longer; excludes random calls)")
            % {"minutes": _QUALIFYING_MINUTES},
        )
        MATCH_CREATED = "match_created", _("Match created")
        MATCH_SUCCESS = "match_success", _("Match success")

    class RepeatScope(models.TextChoices):
        USER = "user", _("Once per user")
        CONTEXT = "context", _("Once per context")

    class ContextType(models.TextChoices):
        LIVE_SESSION = "live_session", _("Live session")
        MATCH = "match", _("Match")

    slug = models.SlugField(
        max_length=64,
        unique=True,
        help_text=_("Stable URL-safe identifier using hyphens, e.g. 'post-call'. Referenced by code and analytics."),
    )
    name = models.CharField(max_length=255, help_text=_("Internal name for the campaign"))

    copy = models.JSONField(
        default=default_campaign_copy,
        help_text=_(
            "User-facing card copy per language: title, description and submit_button. "
            "German is required to go live; English falls back to it. Star captions live in "
            "the frontend locales — they belong to the rating widget, not the campaign."
        ),
    )
    scale = models.PositiveSmallIntegerField(
        default=5,
        validators=[MinValueValidator(MIN_SCALE), MaxValueValidator(MAX_SCALE)],
        help_text=_(
            "Number of stars (2–10). Frozen once a rating has been submitted: growing or shrinking "
            "would change what existing scores mean."
        ),
    )
    questions = models.JSONField(
        default=list,
        help_text=_(
            "Ordered list of {id, type, required, label, placeholder?, options?}. Ids and types "
            "are immutable once answered; labels can always be edited."
        ),
    )

    audience_type = models.CharField(max_length=32, choices=AudienceType.choices, default=AudienceType.ALL)
    audience_value = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text=_(
            "Company name when audience_type is 'company', or a CustomFilterChoices value when "
            "it is 'filter'. Empty for everyone."
        ),
    )

    trigger = models.CharField(max_length=32, choices=Trigger.choices, default=Trigger.ON_SESSION)
    eligible_after_event = models.CharField(
        max_length=32,
        choices=EligibleAfterEvent.choices,
        blank=True,
        default="",
        help_text=_(
            "Named journey condition. Takes effect as soon as the person matches it. "
            "Match conditions count if any of the user's matches qualify; once-per-user "
            "campaigns still offer the survey only once. Timing is controlled with "
            "eligible_after_since."
        ),
    )
    eligible_after_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "Lower bound on when eligible_after_event counts. Only people who reached that "
            "condition on or after this instant are eligible. Empty means any time. Ignored "
            "when the event is empty."
        ),
    )
    repeat_scope = models.CharField(max_length=16, choices=RepeatScope.choices, default=RepeatScope.USER)
    context_type = models.CharField(
        max_length=32,
        choices=ContextType.choices,
        blank=True,
        default="",
        help_text=_("Required when repeat_scope is 'context'."),
    )

    active = models.BooleanField(default=False)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    max_shows = models.PositiveSmallIntegerField(
        default=3,
        help_text=_("How many times an unanswered offer may be presented before it expires."),
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Survey campaign")
        verbose_name_plural = _("Survey campaigns")

    def __str__(self):
        return f"{self.slug} ({'active' if self.active else 'inactive'})"

    # --- state -------------------------------------------------------------------------

    def is_live(self, now=None) -> bool:
        now = now or timezone.now()
        has_started = self.starts_at is None or now >= self.starts_at
        has_not_ended = self.ends_at is None or now <= self.ends_at
        return self.active and has_started and has_not_ended

    @property
    def is_context_scoped(self) -> bool:
        return self.repeat_scope == self.RepeatScope.CONTEXT

    def question_by_id(self, question_id: str) -> dict | None:
        return next((q for q in self.questions if q.get("id") == question_id), None)

    def rating_question_id(self) -> str | None:
        """Question whose answer is mirrored into ``SurveyResponse.rating``."""
        return next((q["id"] for q in self.questions if q.get("type") == QuestionType.RATING), None)

    def text_question_ids(self) -> list[str]:
        """Free-text questions — the answers that must be scrubbed for deleted accounts."""
        return [q["id"] for q in self.questions if q.get("type") == QuestionType.TEXT]

    # --- copy --------------------------------------------------------------------------

    def card_for(self, language: str) -> dict:
        """The card as one user should read it — resolved text, no language dimension left.

        Resolved here rather than in the client because the endpoint already knows whose
        survey it is, which keeps every language rule in one place.
        """
        return {
            "title": resolve_localized(self.copy.get("title"), language),
            "description": resolve_localized(self.copy.get("description"), language),
            "submit_button": resolve_localized(self.copy.get("submit_button"), language),
            "questions": [self._resolve_question(question, language) for question in self.questions],
        }

    @staticmethod
    def _resolve_question(question: dict, language: str) -> dict:
        resolved = {
            "id": question.get("id"),
            "type": question.get("type"),
            "required": bool(question.get("required", False)),
            "label": resolve_localized(question.get("label"), language),
        }
        if question.get("type") == QuestionType.TEXT:
            resolved["placeholder"] = resolve_localized(question.get("placeholder"), language)
        elif question.get("type") == QuestionType.CHOICE:
            resolved["options"] = [
                {"value": option.get("value"), "label": resolve_localized(option.get("label"), language)}
                for option in question.get("options") or []
            ]
        return resolved

    def missing_copy(self) -> list[str]:
        """Human-readable list of what still blocks this campaign from going live.

        A language is all-or-nothing: partially translated copy renders a card with a German
        title above an English question, which reads worse than plain German.
        """
        missing = []
        for field in REQUIRED_CAMPAIGN_COPY_FIELDS:
            if not resolve_localized(self.copy.get(field), PRIMARY_COPY_LANGUAGE):
                missing.append(f"{field} ({PRIMARY_COPY_LANGUAGE})")
        for question in self.questions:
            if not resolve_localized(question.get("label"), PRIMARY_COPY_LANGUAGE):
                missing.append(f"label for '{question.get('id')}' ({PRIMARY_COPY_LANGUAGE})")

        for language in COPY_LANGUAGES:
            if language == PRIMARY_COPY_LANGUAGE:
                continue
            texts = self._texts_for(language)
            if any(texts) and not all(texts):
                missing.append(f"some {language} copy — fill all of it or none of it")
        return missing

    def _texts_for(self, language: str) -> list[str]:
        """Every string a user reads in one language, for the all-or-nothing check."""
        texts = [(self.copy.get(field) or {}).get(language, "") for field in REQUIRED_CAMPAIGN_COPY_FIELDS]
        texts += [(question.get("label") or {}).get(language, "") for question in self.questions]
        for question in self.questions:
            if question.get("type") == QuestionType.CHOICE:
                texts += [(option.get("label") or {}).get(language, "") for option in question.get("options") or []]
        return texts

    # --- validation --------------------------------------------------------------------

    def clean(self):
        super().clean()
        errors: dict[str, list[str]] = {}
        try:
            self._validate_slug()
        except ValidationError as e:
            errors["slug"] = e.messages
        try:
            validate_question_set(self.questions)
        except ValidationError as e:
            errors["questions"] = e.messages
        try:
            self._validate_scope()
        except ValidationError as e:
            errors.setdefault("context_type", []).extend(e.messages)
        try:
            self._validate_audience()
        except ValidationError as e:
            errors.setdefault("audience_value", []).extend(e.messages)
        try:
            self._validate_copy()
        except ValidationError as e:
            errors["copy"] = e.messages
        if not errors:
            # Both only meaningful once the question set and copy are structurally sound.
            try:
                self._validate_answered_questions_unchanged()
            except ValidationError as e:
                errors.setdefault("questions", []).extend(e.messages)
            # Drafts are saved half-finished on purpose; going live is the gate. This is the
            # guarantee that a user never reads a blank or half-translated card.
            if self.active and (missing := self.missing_copy()):
                errors.setdefault("copy", []).append(
                    _("Cannot activate with copy missing: %(missing)s.") % {"missing": "; ".join(missing)}
                )
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Validation lives on the model rather than in admin: an admin-only check is
        # bypassable from a shell, a management command or a data import, and a campaign whose
        # questions changed under existing answers makes those answers unreadable.
        if not self.eligible_after_event:
            self.eligible_after_since = None
        self.full_clean(validate_unique=False)
        super().save(*args, **kwargs)

    def _validate_slug(self):
        """Hyphens only — underscores break URL path segments we reuse this for."""
        if "_" in (self.slug or ""):
            raise ValidationError(_("Use hyphens instead of underscores (e.g. 'post-call')."))

    def _validate_copy(self):
        if not isinstance(self.copy, dict):
            raise ValidationError(_("copy must be an object."))
        # Dropped from the model: captions belong to the star widget, not the campaign row.
        copy = dict(self.copy)
        copy.pop("rating_labels", None)
        self.copy = copy
        unexpected = set(self.copy) - set(CAMPAIGN_COPY_FIELDS)
        if unexpected:
            raise ValidationError(_("copy has unsupported keys: %(keys)s.") % {"keys": sorted(unexpected)})

        for field in CAMPAIGN_COPY_FIELDS:
            validate_localized(self.copy.get(field, {}), field)

    def _validate_scope(self):
        if self.is_context_scoped and not self.context_type:
            raise ValidationError(_("A context-scoped campaign needs a context_type."))
        if not self.is_context_scoped and self.context_type:
            raise ValidationError(_("context_type only applies when repeat_scope is 'context'."))
        # Pending delivery evaluates on_session campaigns with no context in hand, so it has
        # nothing to key a context-scoped offer on. Rejected here rather than left to blow up
        # in the endpoint, where it would take survey delivery down for every user at once.
        if self.is_context_scoped and self.trigger == self.Trigger.ON_SESSION:
            raise ValidationError(
                _("A context-scoped campaign needs an event trigger — there is no context to offer it against.")
            )

    def _validate_audience(self):
        from management.models.custom_banner_event_filters import FILTER_FUNC_MAP

        value = (self.audience_value or "").strip()
        if self.audience_type == self.AudienceType.ALL:
            if value:
                raise ValidationError(_("audience_value only applies to a company or filter audience."))
            return
        if self.audience_type == self.AudienceType.COMPANY:
            if not value:
                raise ValidationError(_("A company audience needs a company in audience_value."))
            return
        if self.audience_type == self.AudienceType.FILTER:
            if value not in FILTER_FUNC_MAP:
                raise ValidationError(_("Unknown audience filter '%(value)s'.") % {"value": value})
            return
        raise ValidationError(_("Unknown audience type '%(type)s'.") % {"type": self.audience_type})

    def _validate_answered_questions_unchanged(self):
        """A question is frozen once anyone has answered it.

        An id present in any response may not disappear from ``questions`` and its type may
        not change — which also covers renames, since a rename is indistinguishable from a
        remove plus an add.         Choice options that appear in answers may not be removed, and
        ``scale`` cannot change once a rating has been submitted.
        """
        stored = type(self).objects.filter(pk=self.pk).first() if self.pk else None
        if stored is None:
            return
        responses = SurveyResponse.objects.filter(campaign_id=self.pk)
        if not responses.exists():
            return

        errors = []
        previous = {q["id"]: q for q in stored.questions if q.get("id")}
        current = {q["id"]: q for q in self.questions if q.get("id")}

        for qid, old_question in previous.items():
            # One indexed existence query per candidate question; there are only ever a few.
            if not responses.filter(answers__has_key=qid).exists():
                continue
            new_question = current.get(qid)
            if new_question is None:
                errors.append(_("Question '%(qid)s' has answers and cannot be removed or renamed.") % {"qid": qid})
                continue
            if new_question.get("type") != old_question.get("type"):
                errors.append(_("Question '%(qid)s' has answers, so its type is fixed.") % {"qid": qid})
                continue
            if new_question.get("type") == QuestionType.CHOICE:
                # Only the values are frozen; option labels are copy and stay editable.
                removed = option_values(old_question) - option_values(new_question)
                used = {
                    value
                    for value in responses.filter(answers__has_key=qid).values_list(f"answers__{qid}", flat=True)
                    if value is not None
                }
                in_use = removed & used
                if in_use:
                    errors.append(
                        _("Options %(options)s of '%(qid)s' appear in answers and cannot be removed.")
                        % {"options": sorted(in_use), "qid": qid}
                    )

        if stored.scale != self.scale and responses.filter(rating__isnull=False).exists():
            errors.append(
                _(
                    "scale cannot change once a rating has been submitted — existing scores would "
                    "no longer mean the same thing."
                )
            )
        if errors:
            raise ValidationError(errors)

    def scale_is_locked(self) -> bool:
        """True once anybody has submitted a rating, which is when changing scale would skew results."""
        if not self.pk:
            return False
        return SurveyResponse.objects.filter(campaign_id=self.pk, rating__isnull=False).exists()


def option_values(question: dict) -> set[str]:
    """The stored answer values of a choice question, ignoring their copy."""
    return {option.get("value") for option in question.get("options") or [] if isinstance(option, dict)}


def validate_localized(value, label: str) -> None:
    """A localized text block: ``{"de": "...", "en": "..."}``, any subset of the languages."""
    if not isinstance(value, dict):
        raise ValidationError(_("%(label)s must be an object of language to text.") % {"label": label})
    unexpected = set(value) - set(COPY_LANGUAGES)
    if unexpected:
        raise ValidationError(
            _("%(label)s has unsupported languages: %(keys)s.") % {"label": label, "keys": sorted(unexpected)}
        )
    for language, text in value.items():
        if not isinstance(text, str):
            raise ValidationError(
                _("%(label)s.%(language)s must be a string.") % {"label": label, "language": language}
            )


def validate_question_set(questions) -> None:
    """Structural validation of a campaign's ``questions`` payload."""
    if not isinstance(questions, list) or not questions:
        raise ValidationError(_("questions must be a non-empty list."))

    seen_ids = set()
    for index, question in enumerate(questions):
        label = f"question {index + 1}"
        if not isinstance(question, dict):
            raise ValidationError(_("%(label)s must be an object.") % {"label": label})

        qid = question.get("id")
        if not isinstance(qid, str) or not QUESTION_ID_PATTERN.match(qid):
            raise ValidationError(
                _("%(label)s has an invalid id — use lower snake_case, e.g. 'comment'.") % {"label": label}
            )
        if qid in seen_ids:
            raise ValidationError(_("Duplicate question id '%(qid)s'.") % {"qid": qid})
        seen_ids.add(qid)

        qtype = question.get("type")
        if qtype not in QuestionType.values:
            raise ValidationError(
                _("Question '%(qid)s' has an unknown type '%(qtype)s'.") % {"qid": qid, "qtype": qtype}
            )
        if not isinstance(question.get("required", False), bool):
            raise ValidationError(_("Question '%(qid)s' has a non-boolean 'required'.") % {"qid": qid})

        unexpected = set(question) - {"id", "type", "required", "label", "placeholder", "options"}
        if unexpected:
            raise ValidationError(
                _("Question '%(qid)s' has unsupported keys: %(keys)s.") % {"qid": qid, "keys": sorted(unexpected)}
            )

        validate_localized(question.get("label", {}), f"label of '{qid}'")
        if "placeholder" in question:
            if qtype != QuestionType.TEXT:
                raise ValidationError(_("Only text questions take a placeholder ('%(qid)s').") % {"qid": qid})
            validate_localized(question["placeholder"], f"placeholder of '{qid}'")

        options = question.get("options")
        if qtype == QuestionType.CHOICE:
            _validate_choice_options(options, qid)
        elif options is not None:
            raise ValidationError(_("Only choice questions take options ('%(qid)s').") % {"qid": qid})


def _validate_choice_options(options, qid: str) -> None:
    """Options are ``{"value": ..., "label": {...}}``: the value is stored in answers and
    immutable, the label is copy and editable."""
    if not isinstance(options, list) or not options:
        raise ValidationError(_("Choice question '%(qid)s' needs options.") % {"qid": qid})

    values = []
    for index, option in enumerate(options):
        if not isinstance(option, dict):
            raise ValidationError(_("Option %(n)s of '%(qid)s' must be an object.") % {"n": index + 1, "qid": qid})
        value = option.get("value")
        if not isinstance(value, str) or not value:
            raise ValidationError(
                _("Option %(n)s of '%(qid)s' needs a non-empty value.") % {"n": index + 1, "qid": qid}
            )
        validate_localized(option.get("label", {}), f"option '{value}' of '{qid}'")
        values.append(value)

    if len(set(values)) != len(values):
        raise ValidationError(_("Option values of '%(qid)s' must be unique.") % {"qid": qid})


class SurveyResponse(models.Model):
    class Status(models.TextChoices):
        SHOWN = "shown", _("Shown")
        SUBMITTED = "submitted", _("Submitted")
        DISMISSED = "dismissed", _("Dismissed")
        EXPIRED = "expired", _("Expired")

    #: Statuses that end the offer. Anything else is re-presentable, capped by ``max_shows``.
    TERMINAL_STATUSES = (Status.SUBMITTED, Status.DISMISSED, Status.EXPIRED)

    campaign = models.ForeignKey(
        SurveyCampaign,
        on_delete=models.PROTECT,
        related_name="responses",
        help_text=_("Retire campaigns with active=False; deleting one would orphan its answers."),
    )
    # Users are soft-deleted (is_active=False, PII scrubbed, row kept), so this FK target
    # always survives and ratings stay in aggregates after an account is closed.
    user = models.ForeignKey("management.User", on_delete=models.CASCADE, related_name="survey_responses")

    context_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text=_("'' for user-scoped surveys, else '<context_type>:<uuid>'."),
    )
    live_session = models.ForeignKey(
        "video.LivekitSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="survey_responses",
        help_text=_("Set for live-session contexts; kept for referential integrity and analytics joins."),
    )

    answers = models.JSONField(default=dict, help_text=_("Complete answer record, keyed by question id."))
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_SCALE)],
        help_text=_("Mirror of the first rating answer, so aggregates read a column not JSON."),
    )

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.SHOWN)
    shown_count = models.PositiveSmallIntegerField(
        default=0,
        help_text=_("Times the client confirmed it displayed the card. Flat at 0 means delivery is broken."),
    )
    shown_at = models.DateTimeField(null=True, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Survey response")
        verbose_name_plural = _("Survey responses")
        constraints = [
            # context_key is '' and never NULL: Postgres treats NULL as distinct from NULL in
            # a unique index, so a nullable column would silently allow unlimited duplicate
            # user-scoped responses — the exact thing this constraint exists to prevent.
            models.UniqueConstraint(
                fields=["campaign", "user", "context_key"],
                name="unique_survey_response_per_context",
            )
        ]
        indexes = [
            models.Index(fields=["campaign", "status"], name="survey_response_campaign_idx"),
            models.Index(fields=["user", "status"], name="survey_response_user_idx"),
        ]

    def __str__(self):
        return f"{self.campaign.slug} / {self.user_id} / {self.status}"

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    def mark_shown(self) -> None:
        """Record that the client actually rendered the card."""
        self.shown_count = (self.shown_count or 0) + 1
        self.shown_at = timezone.now()
        self.save(update_fields=["shown_count", "shown_at", "updated_at"])

    def submit(self, answers: dict) -> None:
        rating_id = self.campaign.rating_question_id()
        self.answers = answers
        self.rating = answers.get(rating_id) if rating_id else None
        self.status = self.Status.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=["answers", "rating", "status", "submitted_at", "updated_at"])

    def dismiss(self) -> None:
        self.status = self.Status.DISMISSED
        self.save(update_fields=["status", "updated_at"])

    def expire(self) -> None:
        self.status = self.Status.EXPIRED
        self.save(update_fields=["status", "updated_at"])
