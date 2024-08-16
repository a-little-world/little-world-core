from management.helpers import IsAdminOrMatchingUser
from rest_framework.decorators import api_view, permission_classes
from django.urls import path
from rest_framework.response import Response
from django.http import HttpResponse
from emails.api_v2.emails_config import EMAILS_CONFIG
from emails.api_v2.render_template import get_full_template_info, render_template_dynamic_lookup
from django.conf import settings
from drf_spectacular.utils import extend_schema, OpenApiParameter
from django.views.decorators.clickjacking import xframe_options_exempt


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def email_config(request):
    return Response(EMAILS_CONFIG.to_dict())


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def show_template_info(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)

    if not template_config:
        return Response({"error": "Template not found"}, status=404)

    return Response(get_full_template_info(template_config))


@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
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
    ]
)
@api_view(["GET"])
@permission_classes([IsAdminOrMatchingUser])
def render_backend_template(request, template_name):
    template_config = EMAILS_CONFIG.emails.get(template_name)

    if not template_config:
        return Response({"error": "Template not found"}, status=404)

    template = template_config.template

    query_params = request.query_params.copy()

    user_id = query_params.get("user_id", None)
    if user_id:
        del query_params["user_id"]

    match_id = query_params.get("match_id", None)
    if match_id:
        del query_params["match_id"]

    context = {}
    for key in query_params:
        context[key] = query_params[key]

    rendered = render_template_dynamic_lookup(template_name, user_id, match_id, **context)
    return HttpResponse(rendered, content_type="text/html")


@api_view(["GET"])
@permission_classes([] if settings.DEBUG else [IsAdminOrMatchingUser])
@xframe_options_exempt
def test_render_email(request, template_name):
    assert settings.DEBUG

    template_config = EMAILS_CONFIG.emails.get(template_name)
    template_info = get_full_template_info(template_config)

    mock_context = {}

    for dep in template_info["dependencies"]:
        context_dependent = dep.get("context_dependent", False)
        if context_dependent:
            mock_context[dep["query_id_field"]] = "Mocked value"

    mock_user_id = 1
    mock_match_id = 2

    rendered = render_template_dynamic_lookup(template_name, mock_user_id, mock_match_id, **mock_context)
    response = HttpResponse(rendered, content_type="text/html")

    # Remove the 'cross-origin-opener-policy' header if it exists in debug
    # This allows the test view to be rendered within an iframe to test the email in testi.at
    if settings.DEBUG:
        if "Cross-Origin-Opener-Policy" in response:
            del response["Cross-Origin-Opener-Policy"]

    return response


api_urls = [
    path("api/matching/emails/config/", email_config),
    path("api/matching/emails/templates/", list_templates),
    path("api/matching/emails/templates/<str:template_name>/", render_backend_template),
    # extra url with .html eding to allow directly testing with testi.at
    path("api/matching/emails/templates/<str:template_name>/info/", show_template_info),
    path("api/matching/emails/templates/<str:template_name>/test/", test_render_email),
]
