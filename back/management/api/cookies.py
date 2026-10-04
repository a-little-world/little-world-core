from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.cache import patch_vary_headers


def get_dynamic_cookie_banner_js(request):
    context = {
        "request": request,
        "hidden_cookie_banner": request.GET.get("hidden", "").lower() == "true",
    }
    code = render_to_string("exporable_cookie_banner_template.js", context)
    response = HttpResponse(code, content_type="application/javascript", charset="utf-8")
    # The payload contains consent-specific state, so it must never be cached or shared between users.
    response["Cache-Control"] = "no-store, max-age=0"
    patch_vary_headers(response, ["Cookie"])
    return response
