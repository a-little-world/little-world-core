"""Merged catalogs, funnels, and legacy list-ID accommodations.

Single lookup point for the API: `get_catalog_entry` resolves legacy IDs, and
`assert_all_domains_strict` is the one validator entry point that every domain
inherits by registering here (see ``dev/docs/analytics_conventions.md`` §8).
"""

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.funnels import FUNNEL_ALLOWED_ROLES, FunnelDefinition
from management.analytics.core.roles import CatalogRole
from management.analytics.signup import queries as signup_q
from management.analytics.signup.catalog import CATALOG as SIGNUP_CATALOG
from management.analytics.signup.funnels import SIGNUP_FUNNEL
from management.models.user import User

_USER = User

# Old public list IDs → canonical catalog keys. API compatibility only; not live definitions.
# Resolved at the view boundary, so callers may send either form.
LEGACY_ALIASES: dict[str, str] = {
    # Bare ID from before domain prefixes were mandatory (conventions §3).
    # Remove once no client sends it — tracked as rollout commit 5.
    "all": "signup__all",
    # Renamed 2026-08-05: the query became the full ineligibility union (A0 German +
    # residence outside Germany), so the German-only name was misleading.
    # Remove once no client sends it — tracked as rollout commit 5.
    "signup__invalid_german_level": "signup__ineligible_for_onboarding",
}

# Legacy journey list IDs owed to callers outside the signup funnel catalog.
#
# These are full definitions, not aliases: the `journey_v2__*` IDs name membership sets
# that no signup__ key covers. They exist here so the catalog can own their labels while
# `USER_JOURNEY_FILTER_LISTS` owns serving them; `assert_all_domains_strict` asserts the
# two agree on the queryset.
#
# Removal condition: delete when the admin panel stops requesting `journey_v2__*` IDs
# (rollout commit 5, deprecation date still unset — see the refactor doc's open decisions).
LEGACY_CATALOG: dict[str, CatalogEntry] = {
    "journey_v2__never_active_or_deleted": CatalogEntry(
        list_id="journey_v2__never_active_or_deleted",
        role=CatalogRole.DROPOUT,
        queryset=signup_q.users_never_active_or_deleted,
        description="Deactivated, deleted, or signups that never verified email.",
        display_name="Never active or deleted",
        base_model=_USER,
    ),
    "journey_v2__email_verified": CatalogEntry(
        list_id="journey_v2__email_verified",
        role=CatalogRole.STAGE,
        queryset=signup_q.users_with_verified_email_form_unfilled,
        description="Email verified; registration form still unfilled (stuck bucket).",
        display_name="Email verified (form incomplete)",
        base_model=_USER,
    ),
    "journey_v2__user_form_completed": CatalogEntry(
        list_id="journey_v2__user_form_completed",
        role=CatalogRole.STAGE,
        queryset=signup_q.users_with_form_complete_awaiting_onboarding_excluding_a0_german,
        description="Form completed, awaiting onboarding, excluding A0 German (legacy journey list).",
        display_name="Form completed (excl. A0 German)",
        base_model=_USER,
    ),
    "journey_v2__too_low_german_level": CatalogEntry(
        list_id="journey_v2__too_low_german_level",
        role=CatalogRole.SEGMENT,
        queryset=signup_q.learners_with_german_level_a0,
        description="All learners with German language level A0 (global segment, not a funnel step).",
        display_name="Learners with A0 German",
        base_model=_USER,
    ),
    "journey_v2__booked_onboarding_call": CatalogEntry(
        list_id="journey_v2__booked_onboarding_call",
        role=CatalogRole.STAGE,
        queryset=signup_q.users_with_booked_onboarding_call,
        description="Future onboarding / prematching call booked.",
        display_name="Booked onboarding call",
        base_model=_USER,
    ),
    "journey_v2__self_onboarding_started": CatalogEntry(
        list_id="journey_v2__self_onboarding_started",
        role=CatalogRole.STAGE,
        queryset=signup_q.users_with_self_onboarding_started,
        description="Self-onboarding started; no future booked call.",
        display_name="Self-onboarding started",
        base_model=_USER,
    ),
    "journey_v2__no_show": CatalogEntry(
        list_id="journey_v2__no_show",
        role=CatalogRole.DROPOUT,
        queryset=signup_q.users_who_no_showed_onboarding,
        description="Booked onboarding but did not attend (past appointment, not onboarded).",
        display_name="Onboarding no-show",
        base_model=_USER,
    ),
}

ALL_CATALOG: dict[str, CatalogEntry] = {**SIGNUP_CATALOG, **LEGACY_CATALOG}

ALL_FUNNELS: tuple[FunnelDefinition, ...] = (SIGNUP_FUNNEL,)

DOMAIN_CATALOGS: dict[str, dict[str, CatalogEntry]] = {
    "signup": SIGNUP_CATALOG,
}


def resolve_list_id(list_id: str) -> str:
    """Map a legacy public list ID to its canonical catalog key (identity if already canonical)."""
    return LEGACY_ALIASES.get(list_id, list_id)


def get_catalog_entry(list_id: str) -> CatalogEntry | None:
    canonical = resolve_list_id(list_id)
    return ALL_CATALOG.get(canonical)


def baseline_list_id(funnel: FunnelDefinition) -> str:
    """The funnel's single BASELINE step — the denominator every other bar is measured against.

    Views must ask for this rather than hardcoding a list ID, so a second domain does not
    need a second copy of the bucket-statistics logic.
    """
    baselines = [
        list_id
        for list_id in funnel.list_ids()
        if (entry := ALL_CATALOG.get(list_id)) is not None and entry.role == CatalogRole.BASELINE
    ]
    if len(baselines) != 1:
        raise AssertionError(f"Funnel {funnel.id!r} must have exactly one baseline step, found {baselines}")
    return baselines[0]


def is_baseline(list_id: str, funnel_baseline_list_id: str) -> bool:
    """True if a caller-supplied (possibly legacy) list ID names the funnel's baseline."""
    return resolve_list_id(list_id) == funnel_baseline_list_id


def funnel_steps_missing_from_catalog(funnel: FunnelDefinition) -> list[str]:
    return [sid for sid in funnel.list_ids() if sid not in ALL_CATALOG]


def funnel_steps_with_disallowed_roles(funnel: FunnelDefinition) -> list[str]:
    """Return list_ids whose catalog role is not allowed as a funnel step.

    Steps missing from the catalog are skipped — ``funnel_steps_missing_from_catalog``
    reports those, and raising ``KeyError`` here would mask the readable error.
    """
    return [
        list_id
        for list_id in funnel.list_ids()
        if (entry := ALL_CATALOG.get(list_id)) is not None and entry.role not in FUNNEL_ALLOWED_ROLES
    ]


def funnel_steps_with_mismatched_base_model(funnel: FunnelDefinition) -> list[str]:
    """Return list_ids whose catalog entity differs from the funnel's (conventions §2)."""
    return [
        list_id
        for list_id in funnel.list_ids()
        if (entry := ALL_CATALOG.get(list_id)) is not None and entry.base_model is not funnel.base_model
    ]


def catalog_keys_with_bad_prefix(domain: str, catalog: dict[str, CatalogEntry]) -> list[str]:
    prefix = f"{domain}__"
    return [key for key in catalog if not key.startswith(prefix)]


def _filter_list_entries() -> dict[str, object]:
    """Public list name → the ``FilterListEntry`` the API serves it with.

    Imported lazily: ``management.api.user_advanced_filter_lists`` imports the query
    modules that ``signup.queries`` also imports, and a module-level import here would
    make the analytics package depend on the API surface it is meant to feed.
    """
    from management.api.user_advanced_filter_lists import FILTER_LISTS

    return {entry.name: entry for entry in FILTER_LISTS}


def catalog_keys_not_servable() -> list[str]:
    """Catalog keys (and legacy aliases) the API has no filter list for.

    This is the coupling that actually breaks the API: a funnel step the view cannot
    look up is a 500, not a validation error.
    """
    servable = _filter_list_entries()
    wanted = set(ALL_CATALOG) | set(LEGACY_ALIASES)
    return sorted(list_id for list_id in wanted if list_id not in servable)


def catalog_keys_disagreeing_with_filter_lists() -> list[str]:
    """Catalog keys whose queryset differs from the one the API serves under that name.

    The catalog owns labels while ``FILTER_LISTS`` owns serving, so the same ID has two
    homes. This asserts they describe the same membership set.
    """
    from management.api.user_advanced_filter_lists import _unwrap_analytics_queryset

    entries = _filter_list_entries()
    bad: list[str] = []
    for list_id, catalog_entry in ALL_CATALOG.items():
        served = entries.get(list_id)
        if served is not None and _unwrap_analytics_queryset(served.queryset) is not catalog_entry.queryset:
            bad.append(list_id)
    return sorted(bad)


def catalog_keys_with_duplicated_description() -> list[str]:
    """Catalog-owned IDs whose filter list also hardcodes a description.

    Two homes for one label is how the catalog/funnel drift happened before
    (conventions §4). The catalog wins at runtime; this makes the dead copy a failure.
    """
    entries = _filter_list_entries()
    return sorted(
        list_id for list_id in ALL_CATALOG if (e := entries.get(list_id)) is not None and e.description is not None
    )


def assert_funnel_valid_strict(funnel: FunnelDefinition) -> None:
    missing = funnel_steps_missing_from_catalog(funnel)
    if missing:
        raise AssertionError(f"Funnel {funnel.id!r} steps missing from catalog: {missing}")

    bad_roles = funnel_steps_with_disallowed_roles(funnel)
    if bad_roles:
        raise AssertionError(f"Funnel {funnel.id!r} steps with disallowed roles: {bad_roles}")

    bad_models = funnel_steps_with_mismatched_base_model(funnel)
    if bad_models:
        raise AssertionError(f"Funnel {funnel.id!r} steps with mismatched base_model: {bad_models}")

    baseline_list_id(funnel)


def assert_all_domains_strict() -> None:
    """Every check a registered domain inherits. Raises on the first violation.

    Called from ``management.tests.test_signup_funnel_analytics``; adding a domain to
    ``DOMAIN_CATALOGS`` / ``ALL_FUNNELS`` is enough to be covered.
    """
    for domain, catalog in DOMAIN_CATALOGS.items():
        bad_keys = catalog_keys_with_bad_prefix(domain, catalog)
        if bad_keys:
            raise AssertionError(f"Domain {domain!r} catalog keys with bad prefix: {bad_keys}")

    for funnel in ALL_FUNNELS:
        assert_funnel_valid_strict(funnel)

    overlap = set(SIGNUP_CATALOG) & set(LEGACY_CATALOG)
    if overlap:
        raise AssertionError(f"LEGACY_CATALOG overlaps SIGNUP_CATALOG: {sorted(overlap)}")

    for alias, canonical in LEGACY_ALIASES.items():
        if canonical not in ALL_CATALOG:
            raise AssertionError(f"LEGACY_ALIASES[{alias!r}] → {canonical!r} not in catalog")
        if alias in ALL_CATALOG:
            raise AssertionError(f"LEGACY_ALIASES[{alias!r}] shadows a live catalog key")

    not_servable = catalog_keys_not_servable()
    if not_servable:
        raise AssertionError(f"Catalog keys with no FILTER_LISTS entry: {not_servable}")

    disagreeing = catalog_keys_disagreeing_with_filter_lists()
    if disagreeing:
        raise AssertionError(f"Catalog and FILTER_LISTS disagree on the queryset for: {disagreeing}")

    duplicated = catalog_keys_with_duplicated_description()
    if duplicated:
        raise AssertionError(
            f"FILTER_LISTS hardcodes a description the catalog already owns (set it to None): {duplicated}"
        )
