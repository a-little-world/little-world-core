from .registry import register


@register("message_action_remove_match")
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
            "by": "admin_task",
            "requesting_user_id": static_params["user_id"],
        }
    ]
    match.save(update_fields=["active", "report_unmatch"])
