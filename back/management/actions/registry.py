import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Callable, Type

_registry: dict[str, "ActionDefinition"] = {}
_task_type_registry: dict[str, "TaskTypeDefinition"] = {}


@dataclass
class ActionDefinition:
    handler: Callable
    static_schema: Type  # dataclass describing static_parameters
    param_schema: Type  # dataclass describing parameters


@dataclass
class TaskTypeDefinition:
    action_type: str
    task_title: Callable[[dict], str]
    task_description: Callable[[dict], str] = field(default_factory=lambda: lambda _: "")


def register(action_type: str, *, static_schema: Type, param_schema: Type):
    """Decorator to register an action handler with its parameter schemas.

    Usage:
        @register("support_reply", static_schema=StaticParams, param_schema=Params)
        def support_reply(static_params: dict, params: dict) -> None:
            ...
    """

    def decorator(fn: Callable) -> Callable:
        _registry[action_type] = ActionDefinition(fn, static_schema, param_schema)
        return fn

    return decorator


def execute(action) -> None:
    """Execute a SupportTaskAction by calling its registered handler."""
    defn = _registry.get(action.action_type)
    if defn is None:
        raise ValueError(f"No handler registered for action_type: '{action.action_type}'")
    defn.handler(action.static_parameters, action.parameters)


def get_action_definition(action_type: str) -> ActionDefinition | None:
    return _registry.get(action_type)


def registered_action_types() -> frozenset[str]:
    return frozenset(_registry)


def register_task_type(
    task_type: str,
    *,
    action_type: str,
    task_title: Callable[[dict], str],
    task_description: Callable[[dict], str] = lambda _: "",
) -> None:
    _task_type_registry[task_type] = TaskTypeDefinition(action_type, task_title, task_description)


def get_task_definition(task_type: str) -> TaskTypeDefinition | None:
    return _task_type_registry.get(task_type)


def registered_task_types() -> frozenset[str]:
    return frozenset(_task_type_registry)


def autodiscover() -> None:
    """Import every module in the actions package to trigger @register decorators."""
    from management import actions as actions_pkg

    for _, module_name, _ in pkgutil.iter_modules(actions_pkg.__path__):
        if module_name != "registry":
            importlib.import_module(f"management.actions.{module_name}")
