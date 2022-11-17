from .cookie_banner_frontend import get_cookie_banner_template_data
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse


def _render_user_form_app(request, app_name, use_cookie_banner=False, **kwargs):
    context = {"app_name": app_name}
    if use_cookie_banner:
        context.update(get_cookie_banner_template_data(request))
    context.update({"kwargs": kwargs if kwargs else {}})
    return render(request, "user_form_frontend.html", context)


# Acessible open page: register, login:

def login(request):
    if request.user.is_authenticated:
        return redirect(reverse("management:main_frontend", kwargs={}))
    return _render_user_form_app(request, "login", use_cookie_banner=True)


def register(request):
    return _render_user_form_app(request, "register", use_cookie_banner=True)

# Inacessible setup pages ( only for loggedin users )


@login_required
def email_verification(request):
    return _render_user_form_app(request, "verifymail", use_cookie_banner=True)


@login_required
def email_change(request):
    return _render_user_form_app(request, "changemail", use_cookie_banner=True)


@login_required
def email_verification_sucess(request):
    return _render_user_form_app(request, "mailverificationsucess")


@login_required
def email_verification_fail(request):
    return _render_user_form_app(request, "mailverificationfail")


def error(request):
    return _render_user_form_app(request, "error")


@login_required
def subsection_of_user_form(request):
    """ This uses some js magic in the user_form app to render only one page of the user form """
    pages = request.GET.get("pages", None)
    # TODO: we might wan't to filter allowed pages,
    # since some pages could be used to delte old userform data,
    # making it unfilled again ( But they could to that anyways with the api directly )
    assert pages, "pages need to provided for this view"
    return _render_user_form_app(request, "oneformpageonly", use_cookie_banner=False, pages=pages)
