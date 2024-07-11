from rest_framework import serializers, status
from django_filters import rest_framework as filters
from drf_spectacular.generators import SchemaGenerator
from django_rest_passwordreset.views import ResetPasswordRequestTokenViewSet
from rest_framework.response import Response
from management.models.user import User
from drf_spectacular.utils import extend_schema, OpenApiResponse
from management.api.user import ChangeEmailSerializer
from translations import get_translation


class CustomResetPasswordRequestTokenViewSet(ResetPasswordRequestTokenViewSet):
    @extend_schema(
        request=ChangeEmailSerializer,
        responses={
            200: OpenApiResponse(
                description="If email exists, token was created successfully."
            ),
            400: OpenApiResponse(description="Invalid email format"),
        },
    )
    def create(self, request, *args, **kwargs):
        serializer = ChangeEmailSerializer(data=request.data)

        if not serializer.is_valid(raise_exception=False):
            return Response(
                {"error": get_translation("api.reset_password_email_not_valid")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        email = serializer.validate_email(serializer.data["email"])

        if not User.objects.filter(email=email).exists():
            return Response(
                {"error": get_translation("api.reset_password_email_try_send")},
                status=status.HTTP_200_OK,
            )

        response = super().create(request, *args, **kwargs)
        if response.status_code == status.HTTP_200_OK:
            return Response(
                {"error": get_translation("api.reset_password_email_try_send")},
                status=status.HTTP_200_OK,
            )


class DynamicFilterSerializer(serializers.Serializer):
    filter_type = serializers.CharField()
    name = serializers.CharField()
    nullable = serializers.BooleanField(default=False)
    value_type = serializers.CharField(required=False)
    description = serializers.CharField(required=False)
    choices = serializers.ListField(child=serializers.DictField(), required=False)
    lookup_expr = serializers.ListField(child=serializers.CharField(), required=False)


def filterset_schema_dict(
    filterset, include_lookup_expr=False, view_key="/api/matching/users/", request=None
):
    _filters = []
    for field_name, filter_instance in filterset.get_filters().items():
        filter_data = {
            "name": field_name,
            "filter_type": type(filter_instance).__name__,
        }

        choices = getattr(filter_instance, "extra", {}).get("choices", [])
        if len(choices):
            filter_data["choices"] = [
                {"tag": choice[1], "value": choice[0]} for choice in choices
            ]

        if "help_text" in filter_instance.extra:
            filter_data["description"] = filter_instance.extra["help_text"]

        if include_lookup_expr:
            if isinstance(filter_instance, filters.RangeFilter):
                filter_data["lookup_expr"] = [
                    "exact",
                    "gt",
                    "gte",
                    "lt",
                    "lte",
                    "range",
                ]
            elif isinstance(filter_instance, filters.BooleanFilter):
                filter_data["lookup_expr"] = ["exact"]
            else:
                filter_data["lookup_expr"] = (
                    [filter_instance.lookup_expr]
                    if isinstance(filter_instance.lookup_expr, str)
                    else filter_instance.lookup_expr
                )
        serializer = DynamicFilterSerializer(data=filter_data)

        serializer.is_valid(raise_exception=True)
        _filters.append(serializer.data)
    # 2 - retrieve the query shema
    generator = SchemaGenerator(patterns=None, urlconf=None)
    schema = generator.get_schema(request=request)
    filter_schemas = (
        schema["paths"].get(view_key, {}).get("get", {}).get("parameters", [])
    )
    for filter_schema in filter_schemas:
        for filter_data in _filters:
            if filter_data["name"] == filter_schema["name"]:
                filter_data["value_type"] = filter_schema["schema"]["type"]
                filter_data["nullable"] = filter_schema["schema"].get("nullable", False)
                break
    return _filters
