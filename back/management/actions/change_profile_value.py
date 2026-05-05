from .registry import register

# Fields that may be safely updated via this action.
# Extend as needed; guards against arbitrary field writes.
ALLOWED_PROFILE_FIELDS = {
    "country_of_residence",
    "birth_year",
    "description",
    "first_name",
    "second_name",
    "phone_mobile",
}


def _do_change_profile_value(static_params: dict, params: dict) -> None:
    from management.models.profile import Profile

    field = static_params["field"]
    new_value = params["new_value"]

    if field not in ALLOWED_PROFILE_FIELDS:
        raise ValueError(f"Field '{field}' is not allowed to be updated via this action.")

    profile = Profile.objects.get(user_id=static_params["user_id"])
    setattr(profile, field, new_value)
    profile.save(update_fields=[field])


@register("message_action_change_profile_value")
def message_action_change_profile_value(static_params: dict, params: dict) -> None:
    """Change an arbitrary profile field following a support message request.

    static_params:
        help_message_id (int)
        user_id (int)
        field (str): profile field name to update

    params:
        new_value: new value for the field
    """
    _do_change_profile_value(static_params, params)


@register("profile_change_action_country_of_residence")
def profile_change_action_country_of_residence(static_params: dict, params: dict) -> None:
    """Update a user's country of residence.

    static_params:
        help_message_id (int)
        user_id (int)
        field (str): always 'country_of_residence'
        current_value (str): current country for display

    params:
        new_value (str): new country of residence
    """
    _do_change_profile_value(static_params, params)
