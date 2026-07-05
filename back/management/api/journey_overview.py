import json
from copy import deepcopy
from pathlib import Path

from django.urls import path
from emails.api.emails_config import EMAILS_CONFIG
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from management.api.match_journey_filter_list import get_match_list_by_name
from management.api.user_advanced_filter_lists import get_list_by_name
from management.helpers import IsAdminOrMatchingUser

DEFINITION_FILE = Path(__file__).resolve().parent.parent / "journey_definitions" / "journey_map.v1.json"


def _load_definition() -> dict:
    with DEFINITION_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _build_list_url(kind: str, list_id: str) -> str:
    if kind == "users":
        return f"/matching/users/?order_by=-date_joined&page_size=50&list={list_id}"
    return f"/matching/matches/?order_by=-created_at&list={list_id}"


def _build_list_meta(kind: str, list_id: str | None) -> dict | None:
    if not list_id:
        return None

    if kind == "users":
        entry = get_list_by_name(list_id)
    else:
        entry = get_match_list_by_name(list_id)

    if not entry:
        return {
            "id": list_id,
            "exists": False,
            "description": None,
            "source_file": None,
            "source_line": None,
            "source_url": None,
            "url": _build_list_url(kind, list_id),
        }

    info = entry.to_dict()
    return {
        "id": list_id,
        "exists": True,
        "description": info.get("description"),
        "source_file": info.get("source_file"),
        "source_line": info.get("source_line"),
        "source_url": info.get("source_url"),
        "url": _build_list_url(kind, list_id),
    }


def _build_email_meta(template_id: str | None) -> dict:
    if not template_id:
        return {
            "id": None,
            "exists": False,
            "subject": None,
            "category_id": None,
            "preview_url": None,
            "api_url": None,
        }

    template = EMAILS_CONFIG.emails.get(template_id)
    return {
        "id": template_id,
        "exists": template is not None,
        "subject": template.subject if template else None,
        "category_id": template.category_id if template else None,
        "preview_url": f"/matching/emails/{template_id}",
        "api_url": f"/api/matching/emails/templates/{template_id}/",
    }


def _enrich_steps(kind: str, steps: list[dict]) -> list[dict]:
    enriched = []
    for step in steps:
        item = deepcopy(step)
        item["list"] = _build_list_meta(kind, item.get("list_id"))
        item["communications"] = [
            {
                **communication,
                "template": _build_email_meta(communication.get("template_id")),
            }
            for communication in item.get("communications", [])
        ]
        enriched.append(item)
    return enriched


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def get_journey_overview(request):
    definition = _load_definition()
    payload = deepcopy(definition)

    user_journey = payload.get("journeys", {}).get("user", {})
    match_journey = payload.get("journeys", {}).get("match", {})

    user_journey["steps"] = _enrich_steps("users", user_journey.get("steps", []))
    match_journey["steps"] = _enrich_steps("matches", match_journey.get("steps", []))

    payload["journeys"]["user"] = user_journey
    payload["journeys"]["match"] = match_journey
    return Response(payload)


api_urls = [
    path("api/matching/journeys/overview/", get_journey_overview),
]
