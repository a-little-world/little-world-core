from enum import StrEnum


class CatalogRole(StrEnum):
    """How a catalog entry may be used.

    - baseline: funnel starting total (usually the domain ``__all`` list)
    - dropout: exit / failure set; safe to subtract in a dropout funnel
    - stage: users currently at a journey step
    - segment: cohort trait (German level, etc.) — not a funnel step long-term
    - composite: combined view of other queries
    """

    BASELINE = "baseline"
    DROPOUT = "dropout"
    STAGE = "stage"
    SEGMENT = "segment"
    COMPOSITE = "composite"
