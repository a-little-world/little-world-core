from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from back.utils import CoolerJson
from ..api.user_data import get_user_data
from ..api.user_slug_filter_lookup import get_users_by_slug_filter
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
    filters = []
    if GET.getlist("filter"):
        filters = GET.getlist("filter")
    else:
        # This also defines the default filter!
        filters = [GET.get("filter", "state.user_form_page:is:0")]

    filtered_user_list = list(User.objects.all())
    for filter in filters:
        filtered_user_list = get_users_by_slug_filter(
            filter_slug=filter, user_to_filter=filtered_user_list)

    page = GET.get("page", 1)
    paginate_by = GET.get("paginate_by", 50)

    # Yes this view is also paginated!
    paginator = Paginator(filtered_user_list, paginate_by)
    pages = paginator.page(page)

    user_list_data = [get_user_data(
        p, is_self=True, admin=True, include_options=False) for p in pages]

    extra_info = {
        "paginate_by": paginate_by,
        "page": page,
        "num_pages": pages.paginator.num_pages,
        "results_total": len(filtered_user_list),
    }

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
