from datetime import timedelta

from django.urls import path
from django.utils import timezone
from drf_spectacular.utils import extend_schema, extend_schema_view
from emails.api.emails_config import EMAILS_CONFIG
from emails.models import DynamicTemplate, DynamicTemplateSerializer, EmailLog
from ipware import get_client_ip as get_ip
from management.api.user_advanced_filter_lists import get_list_by_name
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.dynamic_user_list import DynamicUserList
from management.models.user import User
from management.tasks import send_dynamic_email_backgruound
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response


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

    @action(detail=True, methods=["post"])
    def send(self, request, pk=None, template_name=None):
        # Filter down to current matching user
        qs = User.objects.filter(id__in=self.request.user.state.managed_users.all(), is_active=True)

        user_list = request.data["user_list"]
        if ":dyn:" in user_list:
            qs = DynamicUserList.objects.get(id=user_list.split(":dyn:")[1]).users.all()
        else:
            qs = get_list_by_name(user_list).queryset(qs)

        # 1 - Sanity check that this list contains only unique ids
        user_ids = list(qs.values_list("id", flat=True))
        if len(user_ids) != len(set(user_ids)):
            return Response(
                {"error": "Duplicate user IDs found in the user list. Each user should appear only once."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2 - secondary category based filtering
        count_before = qs.count()
        count_after = count_before

        template = DynamicTemplate.objects.get(template_name=template_name)
        category_id = template.category_id

        if EMAILS_CONFIG.categories[category_id].unsubscribe:
            # meaning the category can be unsubscribed
            qs = qs.exclude(settings__email_settings__unsubscribed_categories__contains=[category_id])
            count_after = qs.count()

        last_dynamic_bulk_emails_send_at = EmailLog.objects.filter(is_dyanmic_email=True).order_by("-time").first()

        # Check if last dynamic bulk email was sent less than 5 minutes ago
        if last_dynamic_bulk_emails_send_at:
            time_since_last_send = timezone.now() - last_dynamic_bulk_emails_send_at.time
            if time_since_last_send < timedelta(minutes=5):
                minutes_remaining = (timedelta(minutes=5) - time_since_last_send).total_seconds() / 60
                return Response(
                    {
                        "error": f"A dynamic bulk email was sent recently. Please wait {minutes_remaining:.1f} more minutes before sending another bulk email.",
                    },
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        # 4 - Security notification that an bulk email is being sent
        ip, routable = get_ip(request)
        security_notification = (
            f"Matching user {request.user.email} is sending a dynamic bulk email to {len(user_ids)} users using ip {ip}"
        )
        from management.tasks import slack_notify_security_channel_async

        slack_notify_security_channel_async.delay(security_notification)

        c = 0
        task_ids = []
        for user in qs:
            task_id = send_dynamic_email_backgruound.delay(template_name, user.id)

            task_ids.append(task_id.task_id)
            c += 1

        return Response(
            {
                "unsubscribe": EMAILS_CONFIG.categories[category_id].unsubscribe,
                "subscribed_user_count": count_after,
                "unsubscribed_user_count": count_before - count_after,
                "task_id": task_ids,
                "message": f"Sent {c} emails",
            }
        )


api_urls = [
    path(
        "api/matching/emails/dynamic_templates/",
        DynamicEmailTemplateViewset.as_view({"get": "list", "post": "create"}),
    ),
    path(
        "api/matching/emails/dynamic_templates/<str:template_name>/",
        DynamicEmailTemplateViewset.as_view({"get": "retrieve", "patch": "partial_update"}),
    ),
    path(
        "api/matching/emails/dynamic_templates/<str:template_name>/send/",
        DynamicEmailTemplateViewset.as_view({"post": "send"}),
    ),
]
