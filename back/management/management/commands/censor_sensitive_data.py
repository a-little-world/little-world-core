"""Overwrite personal data in the database with deterministic placeholders.

Purpose: produce a shareable/seed database from a production copy without leaking
users' personal data. Works on SQLite and PostgreSQL because it goes through the
ORM, and never assumes a table or column layout beyond the model fields listed in
``CENSOR_FIELDS``.

The replacement is deterministic per value (same input -> same output), so unique
constraints and value groupings survive, and re-running is idempotent. Opaque
identifiers that are already pseudonymous and referenced across tables (``id``,
``uuid``, ``hash``, ``old_backend_*``) are deliberately left alone: rewriting them
would break cross-references without removing any real information.

Writes go through ``QuerySet.update()``, not ``Model.save()``, so post_save signals
(which would spawn support tasks, match counters, emails) do not fire.

Dry run by default. Pass ``--apply`` to write.

    python manage.py censor_sensitive_data
    python manage.py censor_sensitive_data --apply

Uploaded files (avatars, chat attachments) are only unlinked in the database; the
blobs remain under MEDIA_ROOT. Delete them separately if the archive includes them.
"""

import hashlib
import uuid
from typing import Any

from django.apps import apps
from django.contrib.auth.hashers import make_password
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand, CommandError

CENSOR_FIELDS: dict[str, list[tuple[str, str]]] = {
    "management.User": [
        ("email", "email"),
        ("username", "text"),
        ("first_name", "name"),
        ("last_name", "name"),
        ("password", "password"),
    ],
    "management.Profile": [
        ("first_name", "name"),
        ("second_name", "name"),
        ("birth_year", "int"),
        ("postal_code", "text"),
        ("phone_mobile", "phone"),
        ("description", "text"),
        ("job_skill_description", "text"),
        ("language_skill_description", "text"),
        ("additional_interests", "text"),
        ("image", "file"),
    ],
    "management.State": [
        ("email_auth_hash", "secret"),
        ("email_auth_pin", "int"),
        ("auto_login_api_token", "secret"),
        ("still_in_contact_form_access_token_user", "uuid"),
        ("prematch_booking_code", "secret"),
        ("company", "text"),
        ("past_emails", "json"),
        ("notes", "text"),
    ],
    "management.HelpMessage": [
        ("message", "text"),
        ("attachment1", "binary"),
        ("attachment2", "binary"),
        ("attachment3", "binary"),
        ("keywords", "json"),
    ],
    "management.SmsModel": [
        ("message", "text"),
        ("twilio_response", "json"),
    ],
    "management.MobileDevice": [
        ("name", "text"),
        ("registration_id", "secret"),
        ("device_id", "int"),
        ("install_id", "uuid"),
        ("model_name", "text"),
    ],
    "management.NewsLetterSubscription": [
        ("email", "email"),
    ],
    "management.PreMatchingAppointment": [
        ("sms_task", "text"),
    ],
    "management.TranslationLog": [
        ("text", "text"),
        ("translation", "text"),
    ],
    "management.SupportTask": [
        ("title", "text"),
        ("description", "text"),
    ],
    "management.SupportTaskAction": [
        ("static_parameters", "json"),
        ("parameters", "json"),
    ],
    "management.SupportTaskNote": [
        ("text", "text"),
    ],
    "management.ObjectHistory": [
        ("old_value", "json"),
        ("new_value", "json"),
    ],
    "management.Match": [
        ("notes", "text"),
        ("report_unmatch", "json"),
        ("auto_marking_updated_logs", "json"),
    ],
    "management.PastMatch": [
        ("reason", "text"),
    ],
    "management.ProposedMatch": [
        ("rejected_reason", "text"),
    ],
    "management.TwoUserMatchingScore": [
        ("scoring_results", "json"),
    ],
    "management.SurveyResponse": [
        ("answers", "json"),
    ],
    "management.MangementTask": [
        ("description", "text"),
    ],
    "management.ShortLinkClick": [
        ("source", "text"),
    ],
    "emails.EmailLog": [
        ("data", "json"),
    ],
    "open_chat.OpenChatConfiguration": [
        ("open_chat_api_key", "secret"),
        ("open_chat_user", "text"),
    ],
    "tracking.Event": [
        ("metadata", "json"),
        ("tags", "json"),
    ],
    "tracking.ConversionEventLog": [
        ("response", "json"),
        ("metadata", "json"),
    ],
    "chat.Message": [
        ("text", "text"),
    ],
    "chat.MessageAttachment": [
        ("file", "file"),
    ],
    "video.LivekitWebhookEvent": [
        ("data", "json"),
    ],
    "video.LivekitSession": [
        ("start_end_before_correction", "text"),
    ],
    "patenmatch.PatenmatchUser": [
        ("first_name", "name"),
        ("last_name", "name"),
        ("postal_code", "text"),
        ("email", "email"),
        ("status_access_token", "secret"),
        ("email_auth_hash", "secret"),
        ("spoken_languages", "text"),
        ("support_for", "text"),
    ],
    "patenmatch.PatenmatchOrganization": [
        ("name", "text"),
        ("postal_code", "text"),
        ("contact_first_name", "name"),
        ("contact_second_name", "name"),
        ("contact_email", "email"),
        ("contact_phone", "phone"),
        ("metadata", "json"),
        ("status_access_token", "secret"),
    ],
    "cookie_consent.LogItem": [
        ("ip_address", "ip"),
    ],
}

# Tables owned by django.contrib whose rows still carry personal data.
DJANGO_PII_TABLES = ["sessions.Session", "admin.LogEntry"]


def _tok(salt: str, value: Any) -> str:
    raw = f"{salt}|{value}".encode("utf-8", "surrogatepass")
    return hashlib.sha256(raw).hexdigest()[:10]


def _censor_json(value: Any, salt: str) -> Any:
    if isinstance(value, dict):
        return {k: _censor_json(v, salt) for k, v in value.items()}
    if isinstance(value, list):
        return [_censor_json(v, salt) for v in value]
    if isinstance(value, str):
        return f"[redacted:{_tok(salt, value)}]"
    return value


def _censor(kind: str, value: Any, salt: str, password_hash: str) -> Any:
    if value is None or value == "":
        return value
    if kind == "json":
        return _censor_json(value, salt)
    if kind == "binary":
        return b""
    if kind == "file":
        return ""
    if kind == "password":
        return password_hash
    if kind == "uuid":
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{salt}|{value}")
    if kind == "int":
        return int(_tok(salt, value), 16) % 1_000_000
    if kind == "ip":
        n = int(_tok(salt, value), 16)
        return f"198.51.100.{n % 253 + 1}"
    if not isinstance(value, str):
        return value
    if kind == "email":
        return f"{_tok(salt, value)}@example.invalid"
    if kind == "phone":
        return "+49" + str(int(_tok(salt, value), 16) % 10**10).zfill(10)
    if kind == "name":
        return "Anon" + _tok(salt, value)[:6]
    if kind == "secret":
        return _tok(salt, value)
    return f"[redacted:{_tok(salt, value)}]"


def _selftest() -> None:
    salt = "s"
    assert _censor("email", "a@b.de", salt, "h") == f"{_tok(salt, 'a@b.de')}@example.invalid"
    assert _censor("email", "a@b.de", salt, "h") == _censor("email", "a@b.de", salt, "h")
    assert _censor("email", "a@b.de", salt, "h") != _censor("email", "c@d.de", salt, "h")
    assert _censor("binary", b"abc", salt, "h") == b""
    assert _censor("json", {"k": ["x", 1], "n": None}, salt, "h")["k"][1] == 1
    assert isinstance(_censor("json", {"k": "x"}, salt, "h")["k"], str)
    assert isinstance(_censor("uuid", uuid.uuid4(), salt, "h"), uuid.UUID)
    assert _censor("password", "whatever", salt, "HASH") == "HASH"
    assert _censor("int", 42, salt, "h") < 1_000_000
    assert _censor("ip", "1.2.3.4", salt, "h").startswith("198.51.100.")
    assert _censor("text", None, salt, "h") is None
    print("selftest ok")


class Command(BaseCommand):
    help = "Overwrite personal data with deterministic placeholders (dry run by default)."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
        parser.add_argument("--salt", default="little-world-censor", help="salt for the deterministic replacements")
        parser.add_argument("--password", default="password123", help="plain password set for every user")
        parser.add_argument(
            "--purge-django-tables",
            action="store_true",
            help="also delete django session rows and admin log entries",
        )
        parser.add_argument("--selftest", action="store_true", help="run transform self-checks and exit")

    def handle(self, **options):
        if options["selftest"]:
            _selftest()
            return

        apply = options["apply"]
        salt = options["salt"]
        password_hash = make_password(options["password"])

        totals = {}
        for label, spec in CENSOR_FIELDS.items():
            app_label, model_name = label.split(".")
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                raise CommandError(f"Unknown model {label}")

            valid_spec = []
            for field_name, kind in spec:
                try:
                    model._meta.get_field(field_name)
                except FieldDoesNotExist:
                    self.stderr.write(f"  ! {label}.{field_name} does not exist, skipping")
                    continue
                valid_spec.append((field_name, kind))
            if not valid_spec:
                continue

            count = 0
            for obj in model.objects.all().iterator():
                updates = {name: _censor(kind, getattr(obj, name), salt, password_hash) for name, kind in valid_spec}
                if apply:
                    model.objects.filter(pk=obj.pk).update(**updates)
                count += 1
            totals[label] = count
            self.stdout.write(f"{'censored' if apply else 'would censor'} {count:>7} {label}")

        if options["purge_django_tables"]:
            for label in DJANGO_PII_TABLES:
                app_label, model_name = label.split(".")
                model = apps.get_model(app_label, model_name)
                count = model.objects.count()
                if apply:
                    model.objects.all().delete()
                totals[label] = count
                self.stdout.write(f"{'purged' if apply else 'would purge'} {count:>9} {label}")

        total = sum(totals.values())
        if not apply:
            self.stdout.write(self.style.WARNING(f"DRY RUN: {total} rows unchanged. Re-run with --apply."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Done. {total} rows censored."))
