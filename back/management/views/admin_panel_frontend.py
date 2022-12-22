from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from back.utils import CoolerJson
from ..api.user_data import get_user_data
from ..api.user_slug_filter_lookup import get_users_by_slug_filter, get_filter_slug_filtered_users_multiple_paginated
from ..models import User
from django.core.paginator import Paginator
import json


@user_passes_test(lambda u: u.is_staff)
def admin_panel(request):
    """
    This renders our sweet admin matching panel 
    We allow it to contain a bunch of 'filters' in the query params
    """
    GET = request.GET
    filters = None
    if GET.getlist("filter"):
        filters = []
    elif GET.get("filter"):
        filters = [GET.get("filter")]
    else:
        filters = ["state.user_form_state:is:filled"]

    user_list_data, extra_info = get_filter_slug_filtered_users_multiple_paginated(
        filters=filters,
        page=GET.get("page", 1),
        paginate_by=GET.get("paginate_by", 50)
    )
    # It is also possible to pass two selectiosn s1=1&s2=2
    if 's1' in GET:
        extra_info['s1'] = GET['s1']

    if 's2' in GET:
        extra_info['s2'] = GET['s2']

    return render(request, "admin_panel_frontend.html",
                  {"user_data": json.dumps({
                      "user_list": user_list_data,
                      "extra_info": extra_info,
                  }, cls=CoolerJson)})
