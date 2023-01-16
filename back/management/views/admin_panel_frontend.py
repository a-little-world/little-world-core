from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from back.utils import CoolerJson
from ..api.user_data import get_user_data
from ..api.user_slug_filter_lookup import get_users_by_slug_filter, get_filter_slug_filtered_users_multiple_paginated
from ..models import User
from .. import controller
from django.core.paginator import Paginator
import json
from ..models import (
    User,
    Profile,
    ProfileSerializer,
    StateSerializer
)


@user_passes_test(lambda u: u.is_staff)
def admin_panel(request):
    """
    This renders our sweet admin matching panel
    We allow it to contain a bunch of 'filters' in the query params
    """
    GET = request.GET
    filters = None
    if GET.getlist("filter"):
        filters = GET.getlist("filter")
    elif GET.get("filter"):
        filters = [GET.get("filter")]
    else:
        filters = ["state.user_form_state:is:filled"]

    user_list_data = []

    bm_user = controller.get_base_management_user()
    extra_info = {
        "filter_options": {
            "profile": ProfileSerializer(bm_user.profile).data["options"],
            "state": StateSerializer(bm_user.state).data["options"],
            # "user": UserSerializer(bm_user).data["options"]
        }
    }
    # It is also possible to pass two selectiosn s1=1&s2=2
    if 'suggest' in GET:
        extra_info['suggest'] = GET['suggest']
        user = controller.get_user_by_hash(GET['suggest'])

        # If we have 's1' we even try to list suggestions
        from ..models.matching_scores import MatchinScore
        suggestions = MatchinScore.matching_suggestion_from_database(user)
        suggested_users = []
        for suggestion in suggestions:
            data = get_user_data(controller.get_user_by_pk(
                int(suggestion["to_usr"])), is_self=True, admin=True)
            suggested_users.append({**data, 'score': suggestion})

        extra_info['suggested_users'] = suggested_users
        extra_info['s1'] = user.hash
        user_list_data = [get_user_data(user, is_self=True, admin=True)]
    elif 'matches' in GET:
        extra_info['matches'] = GET['matches']
        user = controller.get_user_by_hash(GET['matches'])

        # If we have 's1' we even try to list suggestions
        from ..models.matching_scores import MatchinScore

        extra_info['suggested_users'] = [{**get_user_data(
            u, is_self=True, admin=True), "score": []} for u in user.state.matches.all()]
        extra_info['s1'] = user.hash
        user_list_data = [get_user_data(user, is_self=True, admin=True)]
    else:
        user_list_data, _info = get_filter_slug_filtered_users_multiple_paginated(
            filters=filters,
            page=GET.get("page", 1),
            paginate_by=GET.get("paginate_by", 50)
        )
        extra_info.update(_info)

    if 's2' in GET:
        extra_info['s2'] = GET['s2']

    return render(request, "admin_panel_frontend.html",
                  {"user_data": json.dumps({
                      "user_list": user_list_data,
                      "extra_info": extra_info,
                  }, cls=CoolerJson)})


@user_passes_test(lambda u: u.is_staff)
def stats_panel(request):
    """
    Display backend stats
    """
    return render(request, "stats_panel_frontend.html", {})
