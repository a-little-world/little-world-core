from dataclasses import dataclass, field

from .registry import register, register_task_type


@dataclass
class StaticParams:
    help_message_id: int
    user_id: int
    match_id: int


@dataclass
class Params:
    reason: str = field(default="")


@register("message_action_remove_match", static_schema=StaticParams, param_schema=Params)
def message_action_remove_match(static_params: dict, params: dict) -> None:
    """Remove (unmatch) a match following a support message request.

    static_params:
        help_message_id (int)
        user_id (int): the requesting user
        match_id (int)

    params:
        reason (str): reason for removal, logged in match history
    """
    from management.models.matches import Match

    match = Match.objects.get(id=static_params["match_id"])
    match.active = False
    match.report_unmatch = (match.report_unmatch or []) + [
        {
            "kind": "unmatch",
            "reason": params.get("reason", ""),
            "by": "support_task",
            "requesting_user_id": static_params["user_id"],
        }
    ]
    match.save(update_fields=["active", "report_unmatch"])


register_task_type(
    "remove_match",
    action_type="message_action_remove_match",
    task_title=lambda s: f"Remove match #{s['match_id']} — user #{s['user_id']}",
)
