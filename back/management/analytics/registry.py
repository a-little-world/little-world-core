"""Merged catalogs, funnels, and legacy list-ID accommodations.

Single lookup point for the API: `get_catalog_entry` resolves legacy IDs, and
`assert_all_domains_strict` is the one validator entry point that every domain
inherits by registering here (see ``dev/docs/analytics_conventions.md`` §8).
"""

import logging

from management.analytics.core.catalog import CatalogEntry
from management.analytics.core.funnels import FUNNEL_ALLOWED_ROLES, FunnelDefinition
from management.analytics.core.roles import CatalogRole
from management.analytics.user_journey.catalog import CATALOG as USER_JOURNEY_CATALOG
from management.analytics.user_journey.catalog import DOMAIN_PREFIXES as USER_JOURNEY_PREFIXES
from management.analytics.user_journey.funnels import SIGNUP_FUNNEL
from management.analytics.user_journey.partitions import (
    PARTITION_ALLOWED_ROLES,
    USER_JOURNEY_V5,
    PartitionDefinition,
)
from management.analytics.user_journey.queries import funnel as signup_q
from management.models.user import User

logger = logging.getLogger(__name__)

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

ALL_CATALOG: dict[str, CatalogEntry] = {**USER_JOURNEY_CATALOG, **LEGACY_CATALOG}

ALL_FUNNELS: tuple[FunnelDefinition, ...] = (SIGNUP_FUNNEL,)

ALL_PARTITIONS: tuple[PartitionDefinition, ...] = (USER_JOURNEY_V5,)

# Domain → the ID namespaces it owns. A domain may own several: ``user_journey`` keeps
# cumulative funnel stages under ``signup__`` and current-state cells under ``current__``
# because conflating the two is the likeliest way to misread these numbers (§3).
# The prefix is a namespace the domain claims, not a restatement of its name, so
# ``assert_all_domains_strict`` checks that no two domains claim the same one.
DOMAIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "user_journey": USER_JOURNEY_PREFIXES,
}

DOMAIN_CATALOGS: dict[str, dict[str, CatalogEntry]] = {
    "user_journey": USER_JOURNEY_CATALOG,
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
    """Keys that do not sit in one of the namespaces the domain declares."""
    prefixes = DOMAIN_PREFIXES.get(domain, (f"{domain}__",))
    return [key for key in catalog if not key.startswith(prefixes)]


def prefixes_claimed_by_multiple_domains() -> dict[str, list[str]]:
    """Prefix → domains claiming it. Non-empty means two domains can define the same key."""
    claims: dict[str, list[str]] = {}
    for domain, prefixes in DOMAIN_PREFIXES.items():
        for prefix in prefixes:
            claims.setdefault(prefix, []).append(domain)
    return {prefix: domains for prefix, domains in claims.items() if len(domains) > 1}


# ---------------------------------------------------------------------------
# Partitions
# ---------------------------------------------------------------------------


def get_partition(partition_id: str) -> PartitionDefinition | None:
    return next((p for p in ALL_PARTITIONS if p.id == partition_id), None)


def partition_buckets_missing_from_catalog(partition: PartitionDefinition) -> list[str]:
    return [list_id for list_id in partition.all_list_ids() if list_id not in ALL_CATALOG]


def partition_buckets_with_disallowed_roles(partition: PartitionDefinition) -> list[str]:
    """Bucket IDs whose catalog role is not a valid partition cell.

    This is the check that keeps a ``SEGMENT`` out of a partition. V4's
    ``journey_v2__too_low_german_level`` was a cohort trait counted as a state, so it
    overlapped every other bucket by construction.
    """
    return [
        list_id
        for list_id in partition.bucket_ids()
        if (entry := ALL_CATALOG.get(list_id)) is not None and entry.role not in PARTITION_ALLOWED_ROLES
    ]


def partition_buckets_with_mismatched_base_model(partition: PartitionDefinition) -> list[str]:
    return [
        list_id
        for list_id in partition.all_list_ids()
        if (entry := ALL_CATALOG.get(list_id)) is not None and entry.base_model is not partition.base_model
    ]


def assert_partition_valid_strict(partition: PartitionDefinition) -> None:
    """Structural checks only — no database access. See ``compute_partition`` for the data check."""
    missing = partition_buckets_missing_from_catalog(partition)
    if missing:
        raise AssertionError(f"Partition {partition.id!r} buckets missing from catalog: {missing}")

    bad_roles = partition_buckets_with_disallowed_roles(partition)
    if bad_roles:
        raise AssertionError(f"Partition {partition.id!r} buckets with disallowed roles: {bad_roles}")

    bad_models = partition_buckets_with_mismatched_base_model(partition)
    if bad_models:
        raise AssertionError(f"Partition {partition.id!r} buckets with mismatched base_model: {bad_models}")

    baseline = ALL_CATALOG[partition.baseline_list_id]
    if baseline.role is not CatalogRole.BASELINE:
        raise AssertionError(
            f"Partition {partition.id!r} baseline {partition.baseline_list_id!r} has role {baseline.role}"
        )

    duplicates = sorted({bid for bid in partition.bucket_ids() if partition.bucket_ids().count(bid) > 1})
    if duplicates:
        raise AssertionError(f"Partition {partition.id!r} lists the same bucket twice: {duplicates}")


# How many offending IDs a GET response carries. The full set goes to the log.
PARTITION_ID_SAMPLE_LIMIT = 50


def compute_partition(partition: PartitionDefinition, qs, *, sample_limit: int = PARTITION_ID_SAMPLE_LIMIT) -> dict:
    """Count every bucket over ``qs`` and check that they partition the baseline.

    Two things can break and both are reported rather than raised, because one bad row
    must not take down the page (conventions §8): ``overlaps`` when a user is claimed by
    two buckets, and ``uncovered`` when a baseline member is claimed by none. The counts
    are still correct per bucket when either is non-empty, so the caller can render.

    IDs are materialised in Python because the overlap check is pairwise set
    intersection; this is an admin analytics path over one signup cohort, not a hot read.
    """
    baseline_entry = ALL_CATALOG[partition.baseline_list_id]
    baseline_ids = set(baseline_entry.queryset(qs).values_list("id", flat=True))

    bucket_ids: dict[str, set[int]] = {}
    for list_id in partition.bucket_ids():
        bucket_ids[list_id] = set(ALL_CATALOG[list_id].queryset(qs).values_list("id", flat=True))

    ordered = partition.bucket_ids()
    overlaps: dict[str, list[int]] = {}
    for position, name in enumerate(ordered):
        for other in ordered[position + 1 :]:
            shared = bucket_ids[name] & bucket_ids[other]
            if shared:
                overlaps[f"{name}---{other}"] = sorted(shared)

    covered: set[int] = set().union(*bucket_ids.values()) if bucket_ids else set()
    uncovered = sorted(baseline_ids - covered)
    outside = sorted(covered - baseline_ids)

    balanced = not overlaps and not uncovered and not outside
    if not balanced:
        logger.warning(
            "Partition %s does not balance: %d uncovered, %d outside baseline, overlapping pairs %s",
            partition.id,
            len(uncovered),
            len(outside),
            {pair: ids for pair, ids in overlaps.items()},
        )

    return {
        "partition_id": partition.id,
        "baseline_list_id": partition.baseline_list_id,
        "baseline_count": len(baseline_ids),
        "counts": {list_id: len(ids) for list_id, ids in bucket_ids.items()},
        "summed_count": sum(len(ids) for ids in bucket_ids.values()),
        "balanced": balanced,
        "uncovered_count": len(uncovered),
        "uncovered_ids": uncovered[:sample_limit],
        "outside_baseline_count": len(outside),
        "outside_baseline_ids": outside[:sample_limit],
        "overlap_counts": {pair: len(ids) for pair, ids in overlaps.items()},
        "overlap_ids": {pair: ids[:sample_limit] for pair, ids in overlaps.items()},
    }


def assert_partition_balances_strict(partition: PartitionDefinition, qs) -> None:
    """Raise if the partition does not balance over ``qs``. For tests and batch jobs only."""
    result = compute_partition(partition, qs)
    if result["balanced"]:
        return
    raise AssertionError(
        f"Partition {partition.id!r} does not balance over {result['baseline_count']} baseline users: "
        f"{result['uncovered_count']} uncovered {result['uncovered_ids']}, "
        f"{result['outside_baseline_count']} outside baseline {result['outside_baseline_ids']}, "
        f"overlaps {result['overlap_ids']}"
    )


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
    ``DOMAIN_CATALOGS`` / ``ALL_FUNNELS`` / ``ALL_PARTITIONS`` is enough to be covered.

    Structural only — it does not touch the database, so it is safe at import time and in
    ``SimpleTestCase``. The data-level partition check is ``assert_partition_balances_strict``.
    """
    for domain, catalog in DOMAIN_CATALOGS.items():
        bad_keys = catalog_keys_with_bad_prefix(domain, catalog)
        if bad_keys:
            prefixes = DOMAIN_PREFIXES.get(domain, (f"{domain}__",))
            raise AssertionError(f"Domain {domain!r} catalog keys outside its namespaces {prefixes}: {bad_keys}")

    contested = prefixes_claimed_by_multiple_domains()
    if contested:
        raise AssertionError(f"ID prefixes claimed by more than one domain: {contested}")

    for funnel in ALL_FUNNELS:
        assert_funnel_valid_strict(funnel)

    for partition in ALL_PARTITIONS:
        assert_partition_valid_strict(partition)

    domain_keys = [set(catalog) for catalog in DOMAIN_CATALOGS.values()] + [set(LEGACY_CATALOG)]
    seen: set[str] = set()
    for keys in domain_keys:
        collisions = seen & keys
        if collisions:
            raise AssertionError(f"Catalog keys defined in more than one domain: {sorted(collisions)}")
        seen |= keys

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
