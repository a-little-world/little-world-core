"""Registered match-success rule versions.

- ``v0`` — legacy ``completed_match``. Comparison only; not activatable.
- ``v1`` — total mutual call minutes → tokens (active).

Flip ``ACTIVE_VERSION_ID`` to switch what production callers treat as success. Only
versions with ``can_be_active=True`` may be selected — the check below runs at import, so
choosing a comparison-only version fails immediately and says why, rather than surfacing
as an unrelated error from the first caller that asks for a token count.

Pass ``version=`` to compare without changing the default.
"""

from management.match_success.sessions import QUALIFYING_CALL_RULE
from management.match_success.versions import v0_legacy_completed_match, v1_total_minutes
from management.match_success.versions.base import MatchOutcomeVersion

ACTIVE_VERSION_ID = v1_total_minutes.VERSION_ID

#: Intro for the admin docs page. Domain explanation, not a restatement of any one version.
OVERVIEW = (
    "This is the single definition of whether a match succeeded, and"
    "how much activity that represents. Tokens are an activity scale, not the "
    "definition of success: a version may succeed with no token scale at all, or from an "
    "off-platform completion flag or a token threshold. Journeys and the match profiles"
    "are directly tied to the active version of succes, so changing the active version changes these"
    "at once."
)

VERSIONS: dict[str, MatchOutcomeVersion] = {
    v0_legacy_completed_match.VERSION.id: v0_legacy_completed_match.VERSION,
    v1_total_minutes.VERSION.id: v1_total_minutes.VERSION,
}


def get_version(version_id: str | None = None) -> MatchOutcomeVersion:
    resolved = version_id or ACTIVE_VERSION_ID
    try:
        return VERSIONS[resolved]
    except KeyError as exc:
        known = ", ".join(sorted(VERSIONS))
        raise ValueError(f"Unknown match-success version {resolved!r}. Known: {known}") from exc


def list_versions() -> tuple[MatchOutcomeVersion, ...]:
    return tuple(VERSIONS[key] for key in sorted(VERSIONS))


def activatable_version_ids() -> tuple[str, ...]:
    return tuple(sorted(version.id for version in VERSIONS.values() if version.can_be_active))


def documentation() -> dict:
    """Payload for the admin Match Success docs page. Built from the live registry."""
    return {
        "overview": OVERVIEW,
        "qualifying_call_rule": QUALIFYING_CALL_RULE,
        "active_version_id": ACTIVE_VERSION_ID,
        "versions": [version.as_docs(active_id=ACTIVE_VERSION_ID) for version in list_versions()],
    }


def _assert_active_version_is_activatable() -> None:
    active = VERSIONS.get(ACTIVE_VERSION_ID)
    if active is None:
        raise ValueError(
            f"ACTIVE_VERSION_ID is {ACTIVE_VERSION_ID!r}, which is not registered. "
            f"Known: {', '.join(sorted(VERSIONS))}."
        )
    if not active.can_be_active:
        raise ValueError(
            f"ACTIVE_VERSION_ID is {ACTIVE_VERSION_ID!r}, which is comparison-only and has no "
            f"token scale. Activatable versions: {', '.join(activatable_version_ids())}."
        )


_assert_active_version_is_activatable()
