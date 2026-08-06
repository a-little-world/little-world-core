"""Queries for the user-journey domain, split by semantics rather than by chart.

Three modules, and the split is the point:

``traits``
    Predicates both constructs need — "is this learner blocked from matching?".
    Defined once; everything else composes them.
``funnel``
    Cumulative stage reach (``funnel__``). Stages nest, so the bar chart is monotonic.
``state``
    Mutually exclusive current state (``state__``). Cells are disjoint, so they sum
    to the cohort.

The funnel and the partition ask overlapping questions and get different — both
correct — answers. ``funnel.users_who_completed_form`` counts everyone who ever filled
the form; ``state.signup_form_completed`` counts only those still sitting at that step.
Merging them would break either monotonicity or disjointness. What must stay single is
the trait underneath, which is what ``traits`` is for.

Nothing is re-exported here on purpose. ``funnel`` and ``state`` both defined a
``users_all`` at one point, and a flat namespace would have let one silently shadow the
other. Import the module you mean.
"""
