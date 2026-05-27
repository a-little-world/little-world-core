from dataclasses import dataclass, field

from .registry import register, register_task_type


def _execute_change_profile_value(static_params: dict, params: dict) -> None:
    from management.models.profile import Profile

    profile = Profile.objects.get(user_id=static_params["user_id"])
    field_name = static_params["field"]
    setattr(profile, field_name, params["new_value"])
    profile.save(update_fields=[field_name])


@dataclass
class CountryOfResidenceStaticParams:
    help_message_id: int
    user_id: int
    user_name: str
    current_value: str
    field: str = field(default="country_of_residence")


@dataclass
class CountryOfResidenceParams:
    new_value: str


@register(
    "profile_change_action_country_of_residence",
    static_schema=CountryOfResidenceStaticParams,
    param_schema=CountryOfResidenceParams,
)
def profile_change_action_country_of_residence(static_params: dict, params: dict) -> None:
    _execute_change_profile_value(static_params, params)


@dataclass
class ChangeUserTypeStaticParams:
    help_message_id: int
    user_id: int
    user_name: str
    current_value: str
    field: str = field(default="user_type")


@dataclass
class ChangeUserTypeParams:
    new_value: str


@register(
    "message_action_change_user_type", static_schema=ChangeUserTypeStaticParams, param_schema=ChangeUserTypeParams
)
def message_action_change_user_type(static_params: dict, params: dict) -> None:
    from management.models.profile import Profile

    new_type = params["new_value"]
    if new_type not in Profile.TypeChoices:
        raise ValueError(f"Invalid user_type: '{new_type}'.")

    _execute_change_profile_value(static_params, params)


register_task_type(
    "change_country_of_residence",
    action_type="profile_change_action_country_of_residence",
    task_title=lambda s: f"Update country of residence — {s['user_name']}",
    task_description=lambda s: f"Current value: {s['current_value']}",
)

register_task_type(
    "change_user_type",
    action_type="message_action_change_user_type",
    task_title=lambda s: f"Change user type — {s['user_name']}",
    task_description=lambda s: f"Current type: {s['current_value']}",
)
