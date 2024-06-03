from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets
from django.urls import path
from django_filters import rest_framework as filters
from management.models.matches import Match
from management.models.user import User
from management.views.admin_panel_v2 import DetailedPaginationMixin, IsAdminOrMatchingUser
from rest_framework import serializers
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema_view, extend_schema
from dataclasses import dataclass
from drf_spectacular.utils import extend_schema, inline_serializer
from management.api.user_advanced_filter_lists import FILTER_LISTS, FilterListEntry
from management.api.user_data import get_paginated, serialize_proposed_matches, AdvancedUserMatchSerializer
from management.models.unconfirmed_matches import UnconfirmedMatch
from management.models.state import State, StateSerializer
from drf_spectacular.generators import SchemaGenerator
from django.db.models import Q

class AdvancedMatchSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Match
        fields = ['uuid', 'created_at', 'updated_at', 'active', 'confirmed', 'user1', 'user2']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['user1'] = User.objects.get(id=instance.user1.id).email
        representation['user2'] = User.objects.get(id=instance.user2.id).email
        return representation

class MatchFilter(filters.FilterSet):
    
    user1 = filters.ModelChoiceFilter(
        field_name='user1', 
        queryset=User.objects.all(), 
        help_text='Filter for user1'
    )

    user2 = filters.ModelChoiceFilter(
        field_name='user2', 
        queryset=User.objects.all(), 
        help_text='Filter for user2'
    )

    created_between = filters.DateFromToRangeFilter(
        field_name='created_at',
        help_text='Range filter for when the match was created, accepts string datetimes'
    )

    updated_between = filters.DateFromToRangeFilter(
        field_name='updated_at',
        help_text='Range filter for when the match was last updated, accepts string datetimes'
    )

    active = filters.BooleanFilter(
        field_name='active',
        help_text='Filter for active matches'
    )
    
    confirmed = filters.BooleanFilter(
        field_name='confirmed',
        help_text='Filter for confirmed matches'
    )

    class Meta:
        model = Match
        fields = ['uuid', 'created_at', 'updated_at', 'active', 'confirmed', 'user1', 'user2']
        

class DynamicFilterSerializer(serializers.Serializer):
    filter_type = serializers.CharField()
    name = serializers.CharField()
    nullable = serializers.BooleanField(default=False)
    value_type = serializers.CharField(required=False)
    description = serializers.CharField(required=False)
    choices = serializers.ListField(child=serializers.DictField(), required=False)
    lookup_expr = serializers.ListField(child=serializers.CharField(), required=False)

@extend_schema_view(
    list=extend_schema(summary='List matches'),
    retrieve=extend_schema(summary='Retrieve match'),
)
class AdvancedMatchViewset(viewsets.ModelViewSet):
    queryset = Match.objects.all().order_by('-created_at')

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = MatchFilter

    serializer_class = AdvancedMatchSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    def get_queryset(self):
        is_staff = self.request.user.is_staff
        if is_staff:
            return Match.objects.all()
        else:
            return Match.objects.filter(Q(user1=self.request.user) | Q(user2=self.request.user))
        
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

            if 'help_text' in filter_instance.extra:
                filter_data['description'] = filter_instance.extra['help_text']
            
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
        # 2 - retrieve the query schema
        generator = SchemaGenerator(
            patterns=None,
            urlconf=None
        )
        schema = generator.get_schema(request=request)
        view_key = f'/api/matching/matches/'  # derive the view key based on your routing
        filter_schemas = schema['paths'].get(view_key, {}).get('get', {}).get('parameters', [])
        for filter_schema in filter_schemas:
            for filter_data in _filters:
                if filter_data['name'] == filter_schema['name']:
                    filter_data['value_type'] = filter_schema['schema']['type']
                    filter_data['nullable'] = filter_schema['schema'].get('nullable', False)
                    break
        return Response({
            "filters": _filters,
            "lists": [entry.to_dict() for entry in FILTER_LISTS]
        })

    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            return super().get_object()
        else:
            return super().get_queryset().get(uuid=self.kwargs["pk"])

api_urls = [
    path('api/matching/matches/', AdvancedMatchViewset.as_view({'get': 'list'})),
    path('api/matching/matches/filters/', AdvancedMatchViewset.as_view({'get': 'get_filter_schema'})),
    path('api/matching/matches/<pk>/', AdvancedMatchViewset.as_view({'get': 'retrieve'})),
]
