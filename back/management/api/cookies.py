from django.http import HttpResponse
from django.template.loader import render_to_string


def get_dynamic_cookie_banner_js(request):
    context = {"request": request}
    code = render_to_string("exporable_cookie_banner_template.js", context)
    return HttpResponse(code, content_type="application/javascript", charset="utf-8")
