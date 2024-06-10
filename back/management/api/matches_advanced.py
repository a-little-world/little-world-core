from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets
from django.urls import path
from django_filters import rest_framework as filters
from management.models.matches import Match
from management.models.user import User
from management.views.matching_panel import DetailedPaginationMixin, IsAdminOrMatchingUser
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_view, extend_schema, inline_serializer
from management.models.profile import MinimalProfileSerializer
from management.models.state import State
from drf_spectacular.generators import SchemaGenerator
from django.db.models import Q
from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
from management.api.utils_advanced import filterset_schema_dict
from management.controller import unmatch_users

class AdvancedMatchSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Match
        fields = ['uuid', 'created_at', 'updated_at', 'active', 'confirmed', 'user1', 'user2']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user1 = User.objects.get(id=instance.user1.id)
        user2 = User.objects.get(id=instance.user2.id)
        
        representation['user1'] = {
            'id': user1.id,
            'hash': user1.hash,
            'email': user1.email,
            'profile': MinimalProfileSerializer(user1.profile).data
        }
        representation['user2'] = {
            'id': user2.id,
            'hash': user2.hash,
            'email': user2.email,
            'profile': MinimalProfileSerializer(user2.profile).data
        }
        
        if instance.confirmed:
            representation['status'] = 'confirmed'
        elif instance.support_matching:
            representation['status'] = 'support'
        else:
            representation['status'] = 'unconfirmed'
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
        user = self.request.user
        if user.is_staff:
            return Match.objects.all()
        elif user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Match.objects.filter(
                Q(user1__in=user.state.managed_users.all()) | Q(user2__in=user.state.managed_users.all())
            )

    def check_management_user_access(self, match, request):
        user = match.get_partner(request.user)

        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return False, Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=user.pk).exists():
            return False, Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
        return True, None
        
    @action(detail=False, methods=['get'])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # 1 - retrieve all the filters
        filterset = self.filterset_class()
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/matching/matches/", request)

        return Response({
            "filters": _filters,
            "lists": [entry.to_dict() for entry in MATCH_JOURNEY_FILTERS]
        })
        
    @extend_schema(
        summary='Resolve a match',
        request=inline_serializer(
            fields={
                'match_uuid': serializers.UUIDField(),
            }
        ),
    )
    @action(detail=True, methods=['post'])
    def resolve_match(self, request, pk=None):

        self.kwargs['pk'] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res
        
        unmatch_users({
            obj.u1, obj.u2
        }, unmatcher=request.user)
        
        return Response({
            'msg': 'Match resolved'
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
    path('api/matching/matches/<pk>/resolve/', AdvancedMatchViewset.as_view({'post': 'resolve_match'})),
]
