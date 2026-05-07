from dataclasses import dataclass, field
from typing import Any

from .registry import register, register_task_type

# Fields that may be safely updated via this action.
# Extend as needed; guards against arbitrary field writes.
ALLOWED_PROFILE_FIELDS = {
    "country_of_residence",
    "birth_year",
    "description",
    "first_name",
    "second_name",
    "phone_mobile",
    "user_type",
}


def _execute_change_profile_value(static_params: dict, params: dict) -> None:
    from management.models.profile import Profile

    field_name = static_params["field"]
    new_value = params["new_value"]

    if field_name not in ALLOWED_PROFILE_FIELDS:
        raise ValueError(f"Field '{field_name}' is not allowed to be updated via this action.")

    profile = Profile.objects.get(user_id=static_params["user_id"])
    setattr(profile, field_name, new_value)
    profile.save(update_fields=[field_name])


# ─── message_action_change_profile_value ──────────────────────────────────────


@dataclass
class MessageChangeStaticParams:
    help_message_id: int
    user_id: int
    field: str


@dataclass
class MessageChangeParams:
    new_value: Any


@register("message_action_change_profile_value", static_schema=MessageChangeStaticParams, param_schema=MessageChangeParams)
def message_action_change_profile_value(static_params: dict, params: dict) -> None:
    """Change an arbitrary profile field following a support message request.

    static_params:
        help_message_id (int)
        user_id (int)
        field (str): profile field name to update

    params:
        new_value: new value for the field
    """
    _execute_change_profile_value(static_params, params)


# ─── profile_change_action_country_of_residence ───────────────────────────────


@dataclass
class CountryOfResidenceStaticParams:
    help_message_id: int
    user_id: int
    current_value: str
    field: str = field(default="country_of_residence")


@dataclass
class CountryOfResidenceParams:
    new_value: str


@register("profile_change_action_country_of_residence", static_schema=CountryOfResidenceStaticParams, param_schema=CountryOfResidenceParams)
def profile_change_action_country_of_residence(static_params: dict, params: dict) -> None:
    """Update a user's country of residence.

    static_params:
        help_message_id (int)
        user_id (int)
        current_value (str): current country for display
        field (str): always 'country_of_residence'

    params:
        new_value (str): new country of residence
    """
    _execute_change_profile_value(static_params, params)


# ─── message_action_change_user_type ──────────────────────────────────────────


@dataclass
class ChangeUserTypeStaticParams:
    help_message_id: int
    user_id: int
    current_value: str
    field: str = field(default="user_type")


@dataclass
class ChangeUserTypeParams:
    new_value: str


@register("message_action_change_user_type", static_schema=ChangeUserTypeStaticParams, param_schema=ChangeUserTypeParams)
def message_action_change_user_type(static_params: dict, params: dict) -> None:
    """Change a user's type following a support message request.

    static_params:
        help_message_id (int)
        user_id (int)
        current_value (str): current user type for display
        field (str): always 'user_type'

    params:
        new_value (str): new user type
    """
    from management.models.profile import Profile

    new_type = params["new_value"]
    if new_type not in Profile.TypeChoices:
        raise ValueError(f"Invalid user_type: '{new_type}'.")

    _execute_change_profile_value(static_params, params)


# ─── Task type registrations ───────────────────────────────────────────────────

register_task_type(
    "change_profile_value",
    action_type="message_action_change_profile_value",
    task_title=lambda s: f"Change profile value ({s['field']}) — user #{s['user_id']}",
    task_description=lambda s: f"User requested correction of '{s['field']}' via support.",
)

register_task_type(
    "change_country_of_residence",
    action_type="profile_change_action_country_of_residence",
    task_title=lambda s: f"Update country of residence — user #{s['user_id']}",
    task_description=lambda s: f"Current value: {s['current_value']}",
)

register_task_type(
    "change_user_type",
    action_type="message_action_change_user_type",
    task_title=lambda s: f"Change user type — user #{s['user_id']}",
    task_description=lambda s: f"Current type: {s['current_value']}",
)
