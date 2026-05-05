from typing import Callable

_registry: dict[str, Callable] = {}


def register(action_type: str):
    """Decorator to register an action handler by its type string.

    Usage:
        @register("send_support_reply")
        def send_support_reply(static_params: dict, params: dict) -> None:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        _registry[action_type] = fn
        return fn

    return decorator


def execute(action) -> None:
    """Execute an SupportTaskAction by calling its registered handler.

    Raises ValueError if no handler is registered for action.action_type.
    """
    handler = _registry.get(action.action_type)
    if handler is None:
        raise ValueError(f"No handler registered for action_type: '{action.action_type}'")
    handler(action.static_parameters, action.parameters)
