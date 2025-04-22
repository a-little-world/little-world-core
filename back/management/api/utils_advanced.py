from django_filters import rest_framework as filters
from django_rest_passwordreset.views import ResetPasswordRequestTokenViewSet
from drf_spectacular.generators import SchemaGenerator
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from translations import get_translation

from management.api.user import ChangeEmailSerializer
from management.models.user import User


class CustomResetPasswordRequestTokenViewSet(ResetPasswordRequestTokenViewSet):
    @extend_schema(
        request=ChangeEmailSerializer,
        responses={
            200: OpenApiResponse(description="If email exists, token was created successfully."),
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


def filterset_schema_dict(filterset, include_lookup_expr=False, view_key="/api/matching/users/", request=None):
    _filters = []
    for field_name, filter_instance in filterset.get_filters().items():
        filter_data = {
            "name": field_name,
            "filter_type": type(filter_instance).__name__,
        }

        choices = getattr(filter_instance, "extra", {}).get("choices", [])
        if filter_instance.field_name == "userfilter_list":
            choices = choices()

        if len(choices):
            filter_data["choices"] = [{"tag": choice[1], "value": choice[0]} for choice in choices]

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
    
    # 2 - retrieve the query schema
    try:
        generator = SchemaGenerator(patterns=None, urlconf=None)
        print(f"Attempting to generate schema for view_key: {view_key}")
        schema = generator.get_schema(request=request)
        
        # Debug information about available paths
        available_paths = list(schema["paths"].keys())
        print(f"Available schema paths: {available_paths}")
        
        if view_key not in schema["paths"]:
            print(f"WARNING: view_key '{view_key}' not found in schema paths")
            return _filters
            
        filter_schemas = schema["paths"].get(view_key, {}).get("get", {}).get("parameters", [])
        
        # Debug information about the view's schema
        view_info = schema["paths"].get(view_key, {})
        view_methods = list(view_info.keys()) if view_info else []
        print(f"Available methods for {view_key}: {view_methods}")
        
        if "get" not in view_methods:
            print(f"WARNING: 'get' method not found for {view_key}")
        
        # Continue with the original logic
        for filter_schema in filter_schemas:
            for filter_data in _filters:
                if filter_data["name"] == filter_schema["name"]:
                    filter_data["value_type"] = filter_schema["schema"]["type"]
                    filter_data["nullable"] = filter_schema["schema"].get("nullable", False)
                    break
    except AssertionError as e:
        # Detailed information about the assertion error
        import traceback
        print(f"Schema generation assertion error for view_key '{view_key}':")
        print(f"Error message: {str(e)}")
        print("Traceback:")
        traceback.print_exc()
        
        # Try to identify the problematic view
        if "Incompatible AutoSchema used on View" in str(e):
            view_class = str(e).split("View ")[1].split(">")[0] if "View " in str(e) else "unknown"
            print(f"Problematic view class: {view_class}")
            print("This view needs to use drf_spectacular.openapi.AutoSchema")
    except Exception as e:
        # General exception handling with detailed information
        import traceback
        print(f"Unexpected error during schema generation for view_key '{view_key}':")
        print(f"Error type: {type(e).__name__}")
        print(f"Error message: {str(e)}")
        print("Traceback:")
        traceback.print_exc()
    
    return _filters
