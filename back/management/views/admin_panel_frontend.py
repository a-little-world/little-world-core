from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
from ..api.user_data import get_user_data
from ..api.user_slug_filter_lookup import get_users_by_slug_filter
from ..models import User
from django.core.paginator import Paginator
import json

# TODO: set here for now they should be part of the params later!
paginate_by = 50
page = 1


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

    # Yes this view is also paginated!
    # Though you can't yet change the page TODO
    pages = Paginator(filtered_user_list, paginate_by).page(page)

    print(pages[0])

    user_list_data = [get_user_data(
        p, is_self=True, admin=True, include_options=False) for p in pages]

    return render(request, "admin_panel_frontend.html",
                  {"user_data": json.dumps(user_list_data, default=lambda a: str(a))})
