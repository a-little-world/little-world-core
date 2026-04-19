import importlib
from typing import Any

from django.conf import settings
from django.http import HttpResponse
from django.urls import path
from django.views.decorators.clickjacking import xframe_options_exempt
from drf_spectacular.utils import OpenApiParameter, extend_schema
from emails.api.emails_config import EMAILS_CONFIG
from emails.api.render_template import get_full_template_info, render_template_dynamic_lookup
from emails.app_settings import emails_settings
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response


@api_view(["GET"])
@authentication_classes(emails_settings.admin_api_authentication_classes)
@permission_classes(emails_settings.admin_api_permission_classes)
def email_config(request):
    return Response(EMAILS_CONFIG.to_dict())


@api_view(["GET"])
@authentication_classes(emails_settings.admin_api_authentication_classes)
@permission_classes(emails_settings.admin_api_permission_classes)
def show_template_info(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)

    if not template_config:
        return Response({"error": "Template not found"}, status=404)

    return Response(get_full_template_info(template_config))


@api_view(["GET"])
@authentication_classes(emails_settings.admin_api_authentication_classes)
@permission_classes(emails_settings.admin_api_permission_classes)
def list_templates(request):
    templates = []
    for template_name in EMAILS_CONFIG.emails:
        template_config = EMAILS_CONFIG.emails.get(template_name)
        templates.append(get_full_template_info(template_config))
    return Response(templates)


@extend_schema(
    parameters=[
        OpenApiParameter(name="user_id", type=str, location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name="match_id", type=str, location=OpenApiParameter.QUERY, required=False),
        OpenApiParameter(name="proposed_match_id", type=str, location=OpenApiParameter.QUERY, required=False),
    ]
)
@api_view(["GET"])
@authentication_classes(emails_settings.admin_api_authentication_classes)
@permission_classes(emails_settings.admin_api_permission_classes)
def render_backend_template(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)

    if not template_config:
        return Response({"error": "Template not found"}, status=404)

    rendered = render_template_dynamic_lookup(template_name, **request.query_params)
    return HttpResponse(rendered, content_type="text/html")


@api_view(["GET"])
@authentication_classes([] if settings.DEBUG else emails_settings.admin_api_authentication_classes)
@permission_classes([] if settings.DEBUG else emails_settings.admin_api_permission_classes)
@xframe_options_exempt
def test_render_email(request, template_name):
    assert settings.DEBUG

    template_config = EMAILS_CONFIG.emails.get(template_name)
    template_info = get_full_template_info(template_config)

    mock_context = {}

    def _get_mock_dependency_value(dependency_id):
        dependency_config = EMAILS_CONFIG.dependencies.get(dependency_id)
        if dependency_config is None:
            return None

        if not dependency_config.model_source:
            return "Mocked value"

        model_source = dependency_config.model_source.split(".")
        model_module = importlib.import_module(".".join(model_source[:-1]))
        model_or_loader = getattr(model_module, model_source[-1])

        model: Any = (
            model_or_loader()
            if callable(model_or_loader) and not hasattr(model_or_loader, "objects")
            else model_or_loader
        )
        instance = model.objects.order_by("id").first()
        if instance is None:
            return None
        return instance.id

    for dep in template_info["dependencies"]:
        context_dependent = dep.get("context_dependent", False)
        if context_dependent:
            mock_context[dep["query_id_field"]] = "Mocked value"
            continue

        dependency_id = dep.get("id")
        mock_dependency_value = _get_mock_dependency_value(dependency_id)
        if mock_dependency_value is None:
            return Response(
                {"error": f"Could not resolve a mock value for dependency '{dependency_id}'"},
                status=400,
            )
        mock_context[dep["query_id_field"]] = mock_dependency_value

    rendered = render_template_dynamic_lookup(template_name, **mock_context)
    response = HttpResponse(rendered, content_type="text/html")

    # Remove the 'cross-origin-opener-policy' header if it exists in debug
    # This allows the test view to be rendered within an iframe to test the email in testi.at
    if settings.DEBUG:
        if response.has_header("Cross-Origin-Opener-Policy"):
            del response["Cross-Origin-Opener-Policy"]

    return response


@api_view(["GET"])
@authentication_classes(emails_settings.admin_api_authentication_classes)
@permission_classes(emails_settings.admin_api_permission_classes)
def render_logged_email(request, log_id):
    from emails.models import EmailLog

    log = EmailLog.objects.get(pk=log_id)
    return HttpResponse(log.data["html"], content_type="text/html")


api_urls = [
    path("api/matching/emails/config/", email_config),
    path("api/matching/emails/templates/", list_templates),
    path("api/matching/emails/templates/<str:template_name>/", render_backend_template),
    # extra url with .html eding to allow directly testing with testi.at
    path("api/matching/emails/templates/<str:template_name>/info/", show_template_info),
    path("api/matching/emails/templates/<str:template_name>/test/", test_render_email),
    path("api/matching/emails/logs/<int:log_id>/", render_logged_email),
]
