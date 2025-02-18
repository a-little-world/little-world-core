from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.template import Context, Template
from django.urls import path
from drf_spectacular.utils import extend_schema
from emails.api.emails_config import EMAILS_CONFIG
from emails.api.render_template import prepare_template_context, render_template_to_html
from emails.models import EmailLog
from management.helpers import IsAdminOrMatchingUser
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response


class SendEmailSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)
    match_id = serializers.IntegerField(required=False, default=-1)
    proposed_match_id = serializers.IntegerField(required=False, default=None)
    context = serializers.DictField(required=False, default={})
    emulate_send = serializers.BooleanField(required=False, default=False)


class SendEmailDynamicUserListSerializer(serializers.Serializer):
    dynamic_user_list_id = serializers.IntegerField(required=True)
    context = serializers.DictField(required=False, default={})
    emulate_send = serializers.BooleanField(required=False, default=False)


def send_template_email(
    template_name,
    user_id=None,
    match_id=None,
    proposed_match_id=None,
    emulated_send=False,
    context={},
    retrieve_user_model=get_user_model,
):
    user = retrieve_user_model().objects.get(pk=user_id)

    template_info, _context = prepare_template_context(
        template_name,
        user_id,
        match_id,
        proposed_match_id,
        retrieve_user_model=retrieve_user_model,
        **context,
    )
    email_html = render_template_to_html(template_info["config"]["template"], _context)
    subject = Template(template_info["config"]["subject"])
    subject = subject.render(Context(_context))

    from management.controller import get_base_management_user

    # Such that it is also possible to send an email to a 'PatenmatchUser' object
    receiver = user if isinstance(user, get_user_model()) else None

    mail_log = EmailLog.objects.create(
        log_version=1,
        sender=get_base_management_user(),
        receiver=receiver,
        template=template_name,
        data={
            "html": email_html,
            "params": _context,
            "user_id": user_id,
            "match_id": match_id,
            "subject": subject,
        },
    )

    try:
        from_email = EMAILS_CONFIG.senders[template_info["config"]["sender_id"]]
        mail = EmailMessage(
            subject=subject,
            body=email_html,
            from_email=from_email,
            to=[user.email],
        )
        mail.content_subtype = "html"
        if emulated_send:
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
    serializer = SendEmailSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    match_id = None if serializer.data.get("match_id", -1) == -1 else serializer.data.get("match_id", None)
    proposed_match_id = (
        None
        if serializer.data.get("proposed_match_id", None) is None
        else serializer.data.get("proposed_match_id", None)
    )
    return send_template_email(
        template_name,
        user_id=serializer.data["user_id"],
        match_id=match_id,
        proposed_match_id=proposed_match_id,
        emulated_send=serializer.data.get("emulate_send", False),
        context=serializer.data.get("context", {}),
    )


api_urls = [
    path(
        "api/matching/emails/templates/<str:template_name>/send/",
        send_template_email_api,
    ),
]
