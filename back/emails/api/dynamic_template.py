from management.helpers import IsAdminOrMatchingUser, DetailedPaginationMixin
from django.urls import path
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view
from emails.models import DynamicTemplateSerializer, DynamicTemplate
from management.tasks import send_dynamic_email_backgruound
from rest_framework import viewsets
from emails.api.render_template import prepare_dynamic_template_context
from rest_framework.decorators import action
from management.api.user_advanced_filter_lists import get_list_by_name
from management.models.user import User
from emails.api.render_template import render_template_to_html
from django.template import Template, Context
from django.core.mail import EmailMessage
from management.controller import get_base_management_user
from emails.models import EmailLog
from emails.api.emails_config import EMAILS_CONFIG


@extend_schema_view(
    list=extend_schema(summary="List users"),
    retrieve=extend_schema(summary="Retrieve user"),
)
class DynamicEmailTemplateViewset(viewsets.ModelViewSet):
    queryset = DynamicTemplate.objects.all()

    serializer_class = DynamicTemplateSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    lookup_field = "template_name"

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
        
        # 2 - secondary category based filtering
        count_before = qs.count()
        count_after = count_before

        template = DynamicTemplate.objects.get(template_name=template_name)
        category_id = template.category_id
        
        if EMAILS_CONFIG.categories[category_id].unsubscribe:
            # meaning the category can be unsubscribed
            qs = qs.exclude(
                settings__email_settings__unsubscribed_categories__contains=[category_id]
            )
            count_after = qs.count()

        c = 0
        task_ids = []
        for user in qs:
            task_id = send_dynamic_email_backgruound.delay(template_name, user.id)
            
            task_ids.append(task_id.task_id)
            c += 1
        
        return Response({
            "unsubscribe": EMAILS_CONFIG.categories[category_id].unsubscribe,
            "subscribed_user_count": count_after,
            "unsubscribed_user_count": count_before - count_after,
            "task_id": task_ids,
            "message": f"Sent {c} emails"
        })
    


api_urls = [
    path("api/matching/emails/dynamic_templates/", DynamicEmailTemplateViewset.as_view({"get": "list", "post": "create"})),
    path("api/matching/emails/dynamic_templates/<str:template_name>/", DynamicEmailTemplateViewset.as_view({"get": "retrieve", "patch": "partial_update"})),
    path("api/matching/emails/dynamic_templates/<str:template_name>/send/", DynamicEmailTemplateViewset.as_view({"post": "send"}))
]
