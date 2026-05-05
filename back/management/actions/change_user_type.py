from .registry import register


def _do_change_user_type(static_params: dict, params: dict) -> None:
    from management.models.profile import Profile

    new_type = params["new_user_type"]
    if new_type not in ("learner", "volunteer"):
        raise ValueError(f"Invalid user_type: '{new_type}'. Must be 'learner' or 'volunteer'.")

    Profile.objects.filter(user_id=static_params["user_id"]).update(user_type=new_type)


@register("message_action_change_user_type")
def message_action_change_user_type(static_params: dict, params: dict) -> None:
    """Change a user's type following a support message request.

    static_params:
        help_message_id (int)
        user_id (int)

    params:
        new_user_type (str): 'learner' or 'volunteer'
    """
    _do_change_user_type(static_params, params)


@register("profile_action_wrong_user_type")
def profile_action_wrong_user_type(static_params: dict, params: dict) -> None:
    """Correct a user's type when it was detected as wrong.

    static_params:
        user_id (int)
        current_user_type (str)

    params:
        new_user_type (str): 'learner' or 'volunteer'
    """
    _do_change_user_type(static_params, params)
