from emails.mails import templates
from management.views.matching_panel import IsAdminOrMatchingUser
from rest_framework import serializers, status
from django.template.loader import render_to_string
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.core.paginator import Paginator
from back.utils import dataclass_as_dict
from back.utils import _api_url
from django.urls import path, re_path
from dataclasses import dataclass, asdict, fields, MISSING
from management.models.user import User
from back.utils import CoolerJson
import json
from drf_spectacular.utils import extend_schema, OpenApiParameter

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def list_email_templates(request):
    
    serialized = [template.serialized() for template in templates]
    return Response(serialized)

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def get_email_template_params(request, template_name=None):
    template = list(filter(lambda x: x.name == template_name, templates))[0]
    if not template:
        return Response(status=status.HTTP_404_NOT_FOUND)
    
    
    annotations = {field.name: {
        "type" : field.type.__name__,
        "default": field.default if field.default != MISSING else None,
    } for field in fields(template.params)}
    return Response(annotations, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def render_as_email(request, template_name=None):
    template = list(filter(lambda x: x.name == template_name, templates))[0]
    if not template:
        return Response(status=status.HTTP_404_NOT_FOUND)
    
    subject, receiver = request.data.get("subject"), request.data.get("receiver")
    
    del request.data["subject"]
    del request.data["receiver"]
    
    from emails.templates import inject_template_data
    
    mail_params = template.params(**request.data)
    params_injected_text = inject_template_data(
        dataclass_as_dict(template.texts), dataclass_as_dict(mail_params))
    html = render_to_string(template.template, params_injected_text)

    return Response(
        {
            "subject": subject,
            "receiver": receiver,
            "html": html,
        },
        status=status.HTTP_200_OK
    )


class SendEmailRenderedSerializer(serializers.Serializer):
    data = serializers.JSONField(required=False, help_text="Additional parameters depending on the template_name")

    def validate_params(self, value):
        return value

@extend_schema(
    request=SendEmailRenderedSerializer,
)
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def send_email_rendered(request, template_name=None):

    subject, receiver = request.data.get("subject"), request.data.get("receiver")
    receivers = receiver.split(",")
    
    del request.data["subject"]
    del request.data["receiver"]
    
    from emails.mails import send_email, get_mail_data_by_name
    
    send_emails = []
    
    for to in receivers:
        mail_params_data = request.data
        if 'first_name' in mail_params_data:
            mail_params_data['first_name'] = User.objects.get(email=to).profile.first_name
    
        mail_data = get_mail_data_by_name(template_name)
        params = mail_data.params(**mail_params_data)
    
        send_email(
            recivers=[to],
            subject=subject,
            mail_data=mail_data,
            mail_params=params
        )
        
        send_emails.append({
            "to": to,
            "subject": subject,
            "template": template_name,
            "params": mail_params_data.copy()
        })
    return Response({
        "status": "ok",
        "message": "Email sent",
        "info": send_emails
    })
    

    

    

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def list_email_logs(request):
    from emails.models import EmailLog, AdvancedEmailLogSerializer
    
    logs = EmailLog.objects.all().order_by('-time')
    
    if not request.user.is_staff:
        # filter for matching user
        managed_users = request.user.state.managed_users.all()
        logs = logs.filter(receiver__in=managed_users)
        
    # now paginate
    page = Paginator(logs, 20).page(1)
        
    serialized = AdvancedEmailLogSerializer(page, many=True).data
    return Response(serialized)

email_view_routes = [
    path(_api_url('list_emails/logs', admin=True), list_email_logs),
    path(_api_url('list_emails/<str:template_name>/render', admin=True), render_as_email),
    path(_api_url('list_emails/<str:template_name>/send', admin=True), send_email_rendered),
    path(_api_url('list_emails/templates', admin=True), list_email_templates),
    path(_api_url('list_emails/<str:template_name>/params', admin=True), get_email_template_params),
]