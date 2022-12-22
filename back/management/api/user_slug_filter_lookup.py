from typing import List, Optional
from django.core.paginator import Paginator
from .user_data import get_user_data
from ..models import (
    User,
    Profile,
    ProfileSerializer,
    StateSerializer,
    State,
    UserSerializer,
    Room
)
_filter_slug_meta = {
    "is": {"kind": "single"},
    "in": {"kind": "multi"},
    "not": {"kind": "multi"},
    "cut": {"kind": "multi"},
}

FILTER_SLUG_OPERATIONS = list(_filter_slug_meta.keys())

# This defines how 'subjects' can be looked-up
# All these are relative to the user model,
# so 'profile' translates to user.profile python operation
SUBJECT_MAPPINGS = {
    "state": 'state',
    "profile": 'profile',
    "user": None  # <-- The user is the user, doesn't need a lookup
}


def _check_operation_condition(
        operation,
        prop,
        compare_value: Optional[str] = None,
        compare_list: 'Optional[list[str]]' = None):

    assert compare_value or compare_list, "Always require list or value!"
    if _filter_slug_meta[operation]["kind"] == "single":
        assert compare_value
    elif _filter_slug_meta[operation]["kind"] == "multi":
        assert compare_list

    if operation == "is":
        return str(prop) == compare_value
    elif operation == "in":
        return str(prop) in compare_list  # type: ignore
    elif operation == "not":
        return str(prop) != compare_value
    elif operation == "cut":
        return not str(prop) in compare_list  # type: ignore
    return False


def get_filter_slug_filtered_users_multiple(
    filtered_user_list=None,
    filters=[],
):
    if filtered_user_list is None:
        filtered_user_list = list(User.objects.all())
    for filter in filters:
        filtered_user_list = get_users_by_slug_filter(
            filter_slug=filter, user_to_filter=filtered_user_list)
    return filtered_user_list


def get_filter_slug_filtered_users_multiple_paginated(
        filtered_user_list=None,
        filters=[],
        paginate_by=50,
        page=1,
):
    from ..controller import get_base_management_user
    filtered_user_list = get_filter_slug_filtered_users_multiple(
        filtered_user_list=filtered_user_list,
        filters=filters
    )
    paginator = Paginator(filtered_user_list, paginate_by)
    pages = paginator.page(page)

    user_list_data = [get_user_data(
        p, is_self=True, admin=True, include_options=False) for p in pages]

    bm_user = get_base_management_user()

    extra_info = {
        "paginate_by": paginate_by,
        "page": page,
        "num_pages": pages.paginator.num_pages,
        "results_total": len(filtered_user_list),
        "filter_options": {
            "profile": ProfileSerializer(bm_user.profile).data["options"],
            "state": StateSerializer(bm_user.state).data["options"],
            "user": UserSerializer(bm_user).data["options"]
        }
    }

    return user_list_data, extra_info


def get_users_by_slug_filter(
    filter_slug: Optional[str] = None,
    # Per default this would operate on **all** users
    # But when we want to apply multiple filters
    # we will have to be able to pass a limited user list:
    user_to_filter=None
):
    """
    Allowes to filter users by a slug.
    It is generaly assumed that a slug is in the following shape:

    ----> subject:operation:value

    e.g.: state.user_form_state:is:*unfilled
    which is equivalent to state.user_form_state:is:0

    This method tries to make as many smart assumptions as possible
    e.g.: It will automaticly detect wheather a int or a str is used as value
    and make the comparison lookup accordingly
    """
    if not user_to_filter:
        # We have to do this here rather than in parameters
        # cause otherwise this would always try to acess the DB when the code is first loaded
        user_to_filter = list(User.objects.all())
    assert filter_slug and filter_slug.count(":") == 2, "Filterslug wrong!"
    # TODO: we might wan't to handle this more gracefully and return the error

    subject, operation, compare_val = filter_slug.split(":")
    assert operation in FILTER_SLUG_OPERATIONS, f"Unknown operation '{operation}' "
    # multi or single -> on one value or multiple values:
    value_kind = _filter_slug_meta[operation]['kind']

    # Doing this conversion now will save us a lot of compute errort later
    # We always know which type we are dealing with via 'value_kind'
    value = compare_val if value_kind == 'single' else compare_val.split(",")

    # Now we determine the object to operate on
    py_attr = subject.split(".")
    lookup_field = None

    # Currently we do **only** support a nesting level of one!
    for subject_map in SUBJECT_MAPPINGS:
        if subject_map.startswith(py_attr[0]):
            lookup_field = SUBJECT_MAPPINGS[subject_map]

    # Now cause our also is smart and cool we allow to use filter code stings asual
    # Therefore we have to check here is values are numeric
    # and if not we have to convert the to the fitting numeric value
    # Values that should be slug converted are marked with '*' at the beginning
    for v in [value] if isinstance(value, str) else value:
        if v.startswith("*"):
            _v = v[1:]
            try:
                pass  # TODO: finish this functionality!
                #field = getattr(user, lookup_field)
            except:
                assert False, f"Determined slug '{_v}' makrked with '*' but coudn't resolve!"

    filtered_user_list = []

    def _check_for_user(user):
        field = None
        if lookup_field:
            print("User form ", lookup_field)
            field = getattr(user, lookup_field)
        else:
            # None -> means just look on the user model itself
            field = user
        assert field is not None, "Getting field failed"
        try:
            print("Looking up", field, py_attr[1])
            model_value = getattr(field, py_attr[1])
        except Exception as e:
            assert False, f"Getting model value failed for '{py_attr[1]}' {repr(e)}"

        assert model_value is not None, "Model value lookup failed"

        if _check_operation_condition(operation, model_value, compare_list=value) \
                if value_kind == 'multi' else \
            _check_operation_condition(operation, model_value, compare_value=value):
            filtered_user_list.append(user)

    for user in user_to_filter:
        # We catch all these exeption cause it would break the admin panel
        # TODO: but we should log a exception event
        try:
            _check_for_user(user)
        except Exception as e:
            print(f"Exception for user {user} '{repr(e)}' skipping...")
    return filtered_user_list
