from management.helpers import IsAdminOrMatchingUser, DetailedPaginationMixin
from django.urls import path
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, extend_schema_view
from emails.models import DynamicTemplateSerializer, DynamicTemplate
from rest_framework import viewsets


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


api_urls = [
    path("api/matching/emails/dynamic_templates/", DynamicEmailTemplateViewset.as_view({"get": "list", "post": "create", "patch": "partial_update"})),
    path("api/matching/emails/dynamic_templates/<str:template_name>/", DynamicEmailTemplateViewset.as_view({"get": "retrieve"})),
]
