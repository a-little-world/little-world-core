from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets
from django.urls import path
from django_filters import rest_framework as filters
from management.models.user import User
from management.models.profile import Profile
from management.views.admin_panel_v2 import DetailedPaginationMixin, IsAdminOrMatchingUser
from rest_framework import serializers
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema_view, extend_schema

class AdvancedUserSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = User
        fields = ['hash', 'id', 'email', 'date_joined', 'last_login']

class UserFilter(filters.FilterSet):
    
    profile__user_type = filters.ChoiceFilter(field_name='profile__user_type', choices=Profile.TypeChoices.choices)
    state__email_authenticated = filters.BooleanFilter(field_name='state__email_authenticated')
    state__had_prematching_call = filters.BooleanFilter(field_name='state__had_prematching_call')
    joined_between = filters.DateFromToRangeFilter(field_name='date_joined')
    loggedin_between = filters.DateFromToRangeFilter(field_name='last_login')
    state__company = filters.ChoiceFilter(field_name='state__company', choices=[("null", None), ("accenture", "accenture")])

    class Meta:
        model = User
        fields = ['hash', 'id', 'email']
        
from drf_spectacular.generators import SchemaGenerator

class DynamicFilterSerializer(serializers.Serializer):
    filter_type = serializers.CharField()
    name = serializers.CharField()
    nullable = serializers.BooleanField(default=False)
    value_type = serializers.CharField(required=False)
    choices = serializers.ListField(child=serializers.DictField(), required=False)
    lookup_expr = serializers.ListField(child=serializers.CharField(), required=False)

@extend_schema_view(
    list=extend_schema(summary='List users'),
    retrieve=extend_schema(summary='Retrieve user'),
)
class AdvancedUserViewset(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = UserFilter

    serializer_class = AdvancedUserSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    @action(detail=False, methods=['get'])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # 1 - retrieve all the filters
        filterset = self.filterset_class()
        _filters = []
        for field_name, filter_instance in filterset.get_filters().items():
            filter_data = {
                'name': field_name,
                'filter_type': type(filter_instance).__name__,
            }
            
            choices = getattr(filter_instance, 'extra', {}).get('choices', [])
            if len(choices):
                filter_data['choices'] = [{
                    "tag": choice[1],
                    "value": choice[0]
                } for choice in choices]

            
            if include_lookup_expr:
                if isinstance(filter_instance, filters.RangeFilter):
                    filter_data['lookup_expr'] = ['exact', 'gt', 'gte', 'lt', 'lte', 'range']
                elif isinstance(filter_instance, filters.BooleanFilter):
                    filter_data['lookup_expr'] = ['exact']
                else:
                    filter_data['lookup_expr'] = [filter_instance.lookup_expr] if isinstance(filter_instance.lookup_expr, str) else filter_instance.lookup_expr
            serializer = DynamicFilterSerializer(data=filter_data)

            serializer.is_valid(raise_exception=True)
            _filters.append(serializer.data)
        # 2 - retrieve the query shema
        generator = SchemaGenerator(
            patterns=None,
            urlconf=None
        )
        schema = generator.get_schema(request=request)
        view_key = f'/api/matching/users/'  # derive the view key based on your routing
        filter_schemas = schema['paths'].get(view_key, {}).get('get', {}).get('parameters', [])
        for filter_schema in filter_schemas:
            for filter_data in _filters:
                if filter_data['name'] == filter_schema['name']:
                    filter_data['value_type'] = filter_schema['schema']['type']
                    filter_data['nullable'] = filter_schema['schema'].get('nullable', False)
                    break
        return Response({
            "filters": _filters
        })

    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            return super().get_object()
        else:
            return super().get_queryset().get(hash=self.kwargs["pk"])

api_urls = [
    path('api/matching/users/', AdvancedUserViewset.as_view({'get': 'list'})),
    path('api/matching/users/filters/', AdvancedUserViewset.as_view({'get': 'get_filter_schema'})),
    path('api/matching/users/<pk>/', AdvancedUserViewset.as_view({'get': 'retrieve'})),
]