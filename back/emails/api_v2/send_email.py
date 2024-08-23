from django.urls import path
from rest_framework.decorators import api_view, permission_classes
from rest_framework import serializers
from management.helpers import IsAdminOrMatchingUser
from emails.api_v2.render_template import render_template_to_html, prepare_template_context
from drf_spectacular.utils import extend_schema
from emails.models import EmailLog
from rest_framework.response import Response
from django.core.mail import EmailMessage
from emails.api_v2.emails_config import EMAILS_CONFIG
from django.contrib.auth import get_user_model


class SendEmailSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)
    match_id = serializers.IntegerField(required=False, default=None)
    context = serializers.DictField(required=False, default={})
    emulate_send = serializers.BooleanField(required=False, default=False)


def send_template_email(template_name, **kwargs):
    serializer = SendEmailSerializer(data=kwargs)
    serializer.is_valid(raise_exception=True)

    user_id = serializer.validated_data["user_id"]
    match_id = serializer.validated_data.get("match_id", None)
    _context = serializer.validated_data.get("context", {})

    user = get_user_model().objects.get(pk=user_id)

    template_info, context = prepare_template_context(template_name, user_id, match_id, **_context)
    email_html = render_template_to_html(template_info["config"]["template"], context)
    from management.controller import get_base_management_user

    mail_log = EmailLog.objects.create(log_version=1, sender=get_base_management_user(), receiver=user, template=template_name, data={"html": email_html, "params": context, "user_id": user_id, "match_id": match_id})

    try:
        from_email = EMAILS_CONFIG.senders[template_info["config"]["sender_id"]]
        mail = EmailMessage(
            subject=template_info["config"]["subject"],
            body=email_html,
            from_email=from_email,
            to=[user],
        )
        mail.content_subtype = "html"
        if serializer.validated_data.get("emulate_send", False):
            mail_log.data["emulated_send"] = True
        else:
            mail.send(fail_silently=False)
        mail_log.sucess = True
        mail_log.save()
        return Response({"success": True})
    except Exception as e:
        mail_log.sucess = False
        mail_log.save()
        return Response({"error": str(e)}, status=500)


@extend_schema(
    request=SendEmailSerializer,
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def send_template_email_api(request, template_name):
    return send_template_email(template_name, **request.data)


api_urls = [
    path("api/matching/emails/templates/<str:template_name>/send/", send_template_email_api),
]
