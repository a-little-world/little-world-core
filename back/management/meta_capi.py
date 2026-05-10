import hashlib
import json
import logging
import re
import time
from decimal import Decimal
from typing import Any, cast

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def normalize_email(email: str | None) -> str | None:
    if not email:
        return None
    return email.strip().lower()


def normalize_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    return re.sub(r"\D", "", phone)


def normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def normalize_city(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "")


def normalize_state(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def normalize_zip(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower().replace(" ", "")


def normalize_country(value: str | None) -> str | None:
    if not value:
        return None
    return value.strip().lower()


def sha256_hash(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hashed_email(email: str | None) -> str | None:
    return sha256_hash(normalize_email(email))


def hashed_phone(phone: str | None) -> str | None:
    return sha256_hash(normalize_phone(phone))


def hashed_name(value: str | None) -> str | None:
    return sha256_hash(normalize_name(value))


def hashed_city(value: str | None) -> str | None:
    return sha256_hash(normalize_city(value))


def hashed_state(value: str | None) -> str | None:
    return sha256_hash(normalize_state(value))


def hashed_zip(value: str | None) -> str | None:
    return sha256_hash(normalize_zip(value))


def hashed_country(value: str | None) -> str | None:
    return sha256_hash(normalize_country(value))


def get_fbp(request) -> str | None:
    if not request:
        return None
    return request.COOKIES.get("_fbp")


def get_fbc(request) -> str | None:
    if not request:
        return None

    existing_fbc = request.COOKIES.get("_fbc")
    if existing_fbc:
        return existing_fbc

    fbclid = request.GET.get("fbclid")
    if not fbclid:
        return None

    timestamp_ms = int(time.time() * 1000)
    return f"fb.1.{timestamp_ms}.{fbclid}"


def get_client_ip(request) -> str | None:
    if not request:
        return None

    # Trust XFF only when app is deployed behind trusted proxies.
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def get_user_agent(request) -> str | None:
    if not request:
        return None
    return request.META.get("HTTP_USER_AGENT")


def get_event_source_url(request) -> str | None:
    if not request:
        return None
    try:
        return request.build_absolute_uri()
    except Exception:
        return None


def clean_none(obj):
    if isinstance(obj, dict):
        cleaned = {}
        for key, value in obj.items():
            cleaned_value = clean_none(value)
            if cleaned_value is None:
                continue
            if cleaned_value == {}:
                continue
            if cleaned_value == []:
                continue
            cleaned[key] = cleaned_value
        return cleaned

    if isinstance(obj, list):
        cleaned_list = []
        for item in obj:
            cleaned_item = clean_none(item)
            if cleaned_item is None:
                continue
            if cleaned_item == {}:
                continue
            if cleaned_item == []:
                continue
            cleaned_list.append(cleaned_item)
        return cleaned_list

    if isinstance(obj, Decimal):
        return float(obj)

    return obj


def has_marketing_consent(request, user=None) -> bool:
    """
    Consent gate for Meta marketing events.

    Uses the configured consent cookie (``settings.COOKIE_CONSENT_NAME``)
    and only allows events when the ``analytics`` group is accepted.
    """
    if not request:
        return False

    consent_cookie_name = getattr(settings, "COOKIE_CONSENT_NAME", "backend_cookie_consent")
    raw_cookie = request.COOKIES.get(consent_cookie_name)
    if not raw_cookie:
        return False

    normalized_cookie = raw_cookie.strip().strip('"')
    if not normalized_cookie:
        return False

    analytics_value: Any = None
    try:
        consent_payload = json.loads(normalized_cookie)
        if isinstance(consent_payload, dict):
            analytics_value = consent_payload.get("analytics")
    except (TypeError, ValueError):
        cookie_entries = {}
        for entry in normalized_cookie.split("|"):
            if "=" not in entry:
                continue
            key, value = entry.split("=", 1)
            key = key.strip()
            if not key:
                continue
            cookie_entries[key] = value.strip()
        analytics_value = cookie_entries.get("analytics")

    if isinstance(analytics_value, bool):
        return analytics_value

    if analytics_value is None:
        return False

    normalized_analytics = str(analytics_value).strip().lower()
    if normalized_analytics in {"", "-1", "false", "0", "none", "null"}:
        return False
    return True


def build_user_data(
    *,
    request=None,
    user=None,
    email: str | None = None,
    phone: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    city: str | None = None,
    state: str | None = None,
    zip_code: str | None = None,
    country: str | None = None,
    external_id: str | None = None,
    fbp: str | None = None,
    fbc: str | None = None,
    client_ip_address: str | None = None,
    client_user_agent: str | None = None,
) -> dict[str, Any]:
    inferred_email = email
    inferred_phone = phone
    inferred_first_name = first_name
    inferred_last_name = last_name

    if user and getattr(user, "is_authenticated", False):
        inferred_email = inferred_email or getattr(user, "email", None)
        inferred_first_name = inferred_first_name or getattr(user, "first_name", None)
        inferred_last_name = inferred_last_name or getattr(user, "last_name", None)

        profile = getattr(user, "profile", None)
        if profile:
            profile_phone = getattr(profile, "phone_mobile", None)
            inferred_phone = inferred_phone or (str(profile_phone) if profile_phone else None)
            city = city or getattr(profile, "city", None)
            state = state or getattr(profile, "state", None)
            zip_code = zip_code or getattr(profile, "postal_code", None)
            country = country or getattr(profile, "country_of_residence", None)

    user_data = {
        "em": [hashed_email(inferred_email)] if inferred_email else None,
        "ph": [hashed_phone(inferred_phone)] if inferred_phone else None,
        "fn": [hashed_name(inferred_first_name)] if inferred_first_name else None,
        "ln": [hashed_name(inferred_last_name)] if inferred_last_name else None,
        "ct": [hashed_city(city)] if city else None,
        "st": [hashed_state(state)] if state else None,
        "zp": [hashed_zip(zip_code)] if zip_code else None,
        "country": [hashed_country(country)] if country else None,
        "external_id": [sha256_hash(str(external_id))] if external_id else None,
        "client_ip_address": client_ip_address or get_client_ip(request),
        "client_user_agent": client_user_agent or get_user_agent(request),
        "fbp": fbp or get_fbp(request),
        "fbc": fbc or get_fbc(request),
    }

    return cast(dict[str, Any], clean_none(user_data))


def build_event(
    *,
    event_name: str,
    event_id: str,
    user_data: dict[str, Any],
    custom_data: dict[str, Any] | None = None,
    request=None,
    event_time: int | None = None,
    action_source: str = "website",
    event_source_url: str | None = None,
) -> dict[str, Any]:
    event = {
        "event_name": event_name,
        "event_time": event_time or int(time.time()),
        "event_id": event_id,
        "action_source": action_source,
        "event_source_url": event_source_url or get_event_source_url(request),
        "user_data": user_data,
        "custom_data": custom_data or {},
    }
    return cast(dict[str, Any], clean_none(event))


class MetaCAPIError(Exception):
    pass


class MetaCAPIClient:
    def __init__(self):
        self.enabled = settings.META_CAPI_ENABLED
        self.pixel_id = settings.META_PIXEL_ID
        self.access_token = settings.META_CAPI_ACCESS_TOKEN
        self.api_version = settings.META_CAPI_API_VERSION
        self.test_event_code = getattr(settings, "META_CAPI_TEST_EVENT_CODE", "")
        self.timeout = getattr(settings, "META_CAPI_TIMEOUT_SECONDS", 5)

    @property
    def endpoint(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.pixel_id}/events"

    def send_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled:
            logger.info("Meta CAPI disabled; skipping events.")
            return {"skipped": True, "reason": "disabled"}

        if not self.pixel_id:
            raise MetaCAPIError("META_PIXEL_ID is missing.")

        if not self.access_token:
            raise MetaCAPIError("META_CAPI_ACCESS_TOKEN is missing.")

        if not events:
            return {"skipped": True, "reason": "no_events"}

        payload: dict[str, Any] = {"data": events}
        if self.test_event_code:
            payload["test_event_code"] = self.test_event_code
        payload = cast(dict[str, Any], clean_none(payload))

        try:
            response = requests.post(
                self.endpoint,
                params={"access_token": self.access_token},
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.exception("Meta CAPI HTTP request failed.")
            raise MetaCAPIError(str(exc)) from exc

        try:
            response_json = response.json()
        except ValueError:
            response_json = {"raw": response.text}

        if response.status_code >= 400:
            logger.error(
                "Meta CAPI rejected request. status=%s response=%s",
                response.status_code,
                response_json,
            )
            raise MetaCAPIError(response_json)

        logger.info("Meta CAPI sent event batch. count=%s", len(events))
        return response_json
