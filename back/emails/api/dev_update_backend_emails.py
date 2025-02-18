import json

from django.conf import settings
from django.urls import path
from emails.api.emails_config import EMAILS_CONFIG, EmailsConfig
from management.helpers import IsAdminOrMatchingUser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def update_config_json(request):
    if not settings.DEBUG:
        return Response({"error": "This endpoint is only available in DEBUG mode"}, status=400)

    new_config = EmailsConfig.from_dict(request.data)

    with open("emails/emails.json", "w") as f:
        f.write(json.dumps(new_config.to_dict(), indent=2))

    EMAILS_CONFIG = new_config

    return Response(new_config.to_dict())


@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def overwrite_backend_template(request, template_name):
    # Uploads a template html
    if not settings.DEBUG:
        return Response({"error": "This endpoint is only available in DEBUG mode"}, status=400)

    template_html = request.data.get("html")

    template_config = EMAILS_CONFIG.emails.get(template_name)

    if not template_config:
        return Response({"error": "Template not found"}, status=404)

    template_path = template_config.template

    # we have to prefix all the <img src=" attributes with {{ BASE_URL }} so the static base can be set dynamically

    from bs4 import BeautifulSoup

    def prefix_img_src(html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for img in soup.find_all("img"):
            if "src" in img.attrs:
                img["src"] = "{{ BASE_URL }}" + img["src"]

        return str(soup)

    template_html = prefix_img_src(template_html)

    django_template = f"{{% load email_utils %}}{{% get_base_url as BASE_URL %}}{template_html}"

    with open("emails/template/" + template_path, "w+") as f:
        f.write(django_template)

    return Response({"success": True})


api_urls = (
    [
        # DEVELOPMENT ONLY / FOR UPDATING STATIC TEMPLATES
        path("api/matching/emails/templates/<str:template_name>/overwrite/", overwrite_backend_template),
        path("api/matching/emails/config/overwrite/", update_config_json),
    ]
    if settings.DEBUG
    else []
)
