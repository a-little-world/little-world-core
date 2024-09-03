from management.helpers import IsAdminOrMatchingUser, DetailedPaginationMixin
from django.urls import path
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view
from emails.models import DynamicTemplateSerializer, DynamicTemplate
from rest_framework import viewsets
from emails.api_v2.render_template import prepare_dynamic_template_context
from rest_framework.decorators import action
from management.api.user_advanced_filter_lists import get_list_by_name
from management.models.user import User
from emails.api_v2.render_template import render_template_to_html
from django.template import Template, Context
from django.core.mail import EmailMessage
from management.controller import get_base_management_user
from emails.models import EmailLog
from emails.api_v2.emails_config import EMAILS_CONFIG


@extend_schema_view(
    list=extend_schema(summary="List users"),
    retrieve=extend_schema(summary="Retrieve user"),
)
class DynamicEmailTemplateViewset(viewsets.ModelViewSet):
    queryset = DynamicTemplate.objects.all()

    serializer_class = DynamicTemplateSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def retrieve(self, request, *args, **kwargs):
        template_name = kwargs["template_name"]
        template = DynamicTemplate.objects.get(template_name=template_name)
        template_data = DynamicTemplateSerializer(template).data
        return Response(template_data)
    
    @action(detail=True, methods=['post'])
    def send(self, request, pk=None, template_name=None):
        # Filter down to current matching user
        qs = User.objects.filter(id__in=self.request.user.state.managed_users.all(), is_active=True)

        user_list = request.data["user_list"]
        qs = get_list_by_name(user_list).queryset(qs)

        for user in qs:
            dynamic_template_info, _context = prepare_dynamic_template_context(template_name=template_name, user_id=user.id)
            html_template = Template(dynamic_template_info["template"])
            html = html_template.render(Context(_context))
            subject = Template(dynamic_template_info["subject"])
            subject = subject.render(Context(_context))

            mail_log = EmailLog.objects.create(log_version=1, sender=get_base_management_user(), receiver=user, template=template_name, data={"html": html, "params": _context, "user_id": user.id, "match_id": None, "subject": subject})

            try:
                from_email = EMAILS_CONFIG.senders["noreply"]
                mail = EmailMessage(
                    subject=subject,
                    body=html,
                    from_email=from_email,
                    to=[user],
                )
                mail.content_subtype = "html"
                mail.send(fail_silently=False)
                mail_log.sucess = True
                mail_log.save()
            except Exception as e:
                mail_log.sucess = False
                mail_log.save()
        
        return Response("Send Emails")
    


api_urls = [
    path("api/matching/emails/dynamic_templates/", DynamicEmailTemplateViewset.as_view({"get": "list", "post": "create", "patch": "partial_update"})),
    path("api/matching/emails/dynamic_templates/<str:template_name>/", DynamicEmailTemplateViewset.as_view({"get": "retrieve"})),
    path("api/matching/emails/dynamic_templates/<str:template_name>/send/", DynamicEmailTemplateViewset.as_view({"post": "send"}))
]
