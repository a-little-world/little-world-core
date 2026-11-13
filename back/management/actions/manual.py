from dataclasses import dataclass

from .registry import register


@dataclass
class StaticParams:
    pass


@dataclass
class Params:
    pass


@register("manual", static_schema=StaticParams, param_schema=Params)
def manual(static_params: dict, params: dict) -> None:
    """No-op handler for generic TODO tasks.

    A manual task has no side effect of its own; executing the action simply
    resolves it and completes the task via the normal action flow.
    """
    return None
