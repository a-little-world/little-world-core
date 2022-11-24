from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render
import json


@user_passes_test(lambda u: u.is_staff)
def render_admin_panel(request):

    user_list_data = None
    return render(request, "admin_panel_frontend.html",
                  {"user_data": json.dumps(user_list_data)})
