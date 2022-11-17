from .cookie_banner_frontend import get_cookie_banner_template_data
from django.shortcuts import render, redirect
from django.urls import reverse


def _render_user_form_app(request, app_name, use_cookie_banner=False, **kwargs):
    context = {"app_name": app_name}
    if use_cookie_banner:
        context.update(get_cookie_banner_template_data(request))
    context.update({"kwargs": kwargs if kwargs else {}})
    return render(request, "user_form_frontend.html", context)


def login(request):
    # TODO: track event
    # if request.user.is_authenticated:
    #    return redirect(reverse("management:main_frontend", kwargs={}))

    return _render_user_form_app(request, "login", use_cookie_banner=True)


def register(request):
    return _render_user_form_app(request, "register", use_cookie_banner=False)
