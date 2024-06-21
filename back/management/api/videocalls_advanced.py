from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets
from django.urls import path
from django_filters import rest_framework as filters
from video.models import LivekitSession
from management.models.user import User
from management.views.matching_panel import DetailedPaginationMixin, IsAdminOrMatchingUser
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_view, extend_schema, inline_serializer
from management.models.profile import MinimalProfileSerializer
from management.models.state import State
from drf_spectacular.generators import SchemaGenerator
from django.db.models import Q
from management.api.utils_advanced import filterset_schema_dict

class AdvancedLivekitSessionSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = LivekitSession
        fields = ['uuid', 'created_at', 'end_time', 'is_active', 'u1', 'u2', 'both_have_been_active']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        u1 = User.objects.get(id=instance.u1.id)
        u2 = User.objects.get(id=instance.u2.id)
        
        representation['u1'] = {
            'id': u1.id,
            'hash': u1.hash,
            'email': u1.email,
            'profile': MinimalProfileSerializer(u1.profile).data
        }
        representation['u2'] = {
            'id': u2.id,
            'hash': u2.hash,
            'email': u2.email,
            'profile': MinimalProfileSerializer(u2.profile).data
        }
        
        if instance.is_active:
            representation['status'] = 'active'
        else:
            representation['status'] = 'inactive'
            
        representation['both_have_been_active'] = instance.both_have_been_active
        
        # calculate the duration of the session

        if instance.end_time:
            duration = instance.end_time - instance.created_at
            minutes, seconds = divmod(duration.seconds, 60)
            representation['duration'] = f"{minutes} minutes, ({seconds} s)"
        else:
            representation['duration'] = None
        return representation

class LivekitSessionFilter(filters.FilterSet):
    
    u1 = filters.ModelChoiceFilter(
        field_name='u1', 
        queryset=User.objects.all(), 
        help_text='Filter for u1'
    )

    u2 = filters.ModelChoiceFilter(
        field_name='u2', 
        queryset=User.objects.all(), 
        help_text='Filter for u2'
    )

    created_between = filters.DateFromToRangeFilter(
        field_name='created_at',
        help_text='Range filter for when the session was created, accepts string datetimes'
    )

    ended_between = filters.DateFromToRangeFilter(
        field_name='end_time',
        help_text='Range filter for when the session ended, accepts string datetimes'
    )

    active = filters.BooleanFilter(
        field_name='is_active',
        help_text='Filter for active sessions'
    )
    
    class Meta:
        model = LivekitSession
        fields = ['uuid', 'created_at', 'end_time', 'is_active', 'u1', 'u2']
    
        
@extend_schema_view(
    list=extend_schema(summary='List Livekit sessions'),
    retrieve=extend_schema(summary='Retrieve Livekit session'),
)
class AdvancedVideoCallsViewset(viewsets.ModelViewSet):
    queryset = LivekitSession.objects.all().order_by('-created_at')

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = LivekitSessionFilter

    serializer_class = AdvancedLivekitSessionSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return LivekitSession.objects.all()
        elif user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return LivekitSession.objects.filter(
                Q(u1__in=user.state.managed_users.all()) | Q(u2__in=user.state.managed_users.all())
            )

    def check_management_user_access(self, session, request):
        user = session.get_partner(request.user)

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
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/video-calls/livekit-sessions/", request)

        return Response({
            "filters": _filters,
            "lists": []
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
    path('api/matching/video_calls/', AdvancedVideoCallsViewset.as_view({'get': 'list'})),
    path('api/matching/video_calls/filters/', AdvancedVideoCallsViewset.as_view({'get': 'get_filter_schema'})),
    path('api/matching/video_calls/<str:pk>/', AdvancedVideoCallsViewset.as_view({'get': 'retrieve'})),
]