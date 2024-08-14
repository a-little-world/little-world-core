from rest_framework import viewsets, serializers
from django_filters import rest_framework as filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.urls import path
from django.utils import timezone
from management.models.pre_matching_appointment import PreMatchingAppointment
from django.contrib.auth import get_user_model
from management.views.matching_panel import DetailedPaginationMixin
from management.helpers import IsAdminOrMatchingUser
from management.models.profile import MinimalProfileSerializer
from management.api.user_advanced import AdvancedUserSerializer

from drf_spectacular.utils import extend_schema_view, extend_schema, inline_serializer
from management.api.utils_advanced import filterset_schema_dict
import uuid

class PreMatchingAppointmentSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = PreMatchingAppointment
        fields = ['uuid', 'start_time', 'end_time', 'created', 'user']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user = instance.user
        
        representation['user'] = AdvancedUserSerializer(user).data
        representation['had_prematching_call'] = user.state.had_prematching_call

        return representation

class PreMatchingAppointmentFilter(filters.FilterSet):

    start_time = filters.DateFromToRangeFilter(
        field_name='start_time',
        help_text='Range filter for start time'
    )

    end_time = filters.DateFromToRangeFilter(
        field_name='end_time',
        help_text='Range filter for end time'
    )
    
    list = filters.DateTimeFilter(
        field_name='start_time',
        lookup_expr='date',
    )

    order_by = filters.OrderingFilter(
        fields=(
            ('start_time', 'start_time'),
            ('end_time', 'end_time'),
        ),
        help_text='Ordering filter for appointments'
    )  

    class Meta:
        model = PreMatchingAppointment
        fields = ['start_time', 'end_time', 'user']
    
        
@extend_schema_view(
    list=extend_schema(summary='List PreMatchingAppointments'),
    retrieve=extend_schema(summary='Retrieve PreMatchingAppointment'),
)
class PreMatchingAppointmentViewSet(viewsets.ModelViewSet):
    queryset = PreMatchingAppointment.objects.all().order_by('-created')
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = PreMatchingAppointmentFilter
    serializer_class = PreMatchingAppointmentSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    def get_queryset(self):
        user = self.request.user

        from management.models.state import State
        if user.is_staff:
            return PreMatchingAppointment.objects.all()
        elif user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return PreMatchingAppointment.objects.filter(user__in=user.state.managed_users.all())

    def check_management_user_access(self, appointment, request):

        from management.models.state import State
        user = appointment.user

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
        # Retrieve all the filters
        filterset = self.filterset_class()
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/prematchingappointments/", request)
        

        # Here we actally generate the filter list dynamicly.
        # We start of by grouping the together the 10 most recent start_times
        
        top_x = 40
        start_times = PreMatchingAppointment.objects.all().order_by('-start_time').values_list('start_time', flat=True).distinct()[:top_x]
        from management.api.user_advanced_filter_lists import FilterListEntry
        
        filter_lists = []
        for start_time in start_times:
            filter_lists.append(FilterListEntry(
                name=str(start_time),
                description=start_time,
                queryset=lambda qs: qs.filter(start_time=start_time)
            ).to_dict())

        return Response({
            "filters": _filters,
            "lists": filter_lists
        })
        
    @extend_schema(
        summary='Resolve an appointment',
        request=inline_serializer(
            name='ResolveAppointmentRequest',
            fields={
                'appointment_uuid': serializers.UUIDField(),
            }
        ),
    )
    @action(detail=True, methods=['post'])
    def resolve_appointment(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res
        
        # Implement your resolve logic here
        return Response({
            'msg': 'Appointment resolved'
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
    path('api/matching/prematchingappointments/', PreMatchingAppointmentViewSet.as_view({'get': 'list'})),
    path('api/matching/prematchingappointments/filters/', PreMatchingAppointmentViewSet.as_view({'get': 'get_filter_schema'})),
    path('api/matching/prematchingappointments/<pk>/', PreMatchingAppointmentViewSet.as_view({'get': 'retrieve'})),
    path('api/matching/prematchingappointments/<pk>/resolve/', PreMatchingAppointmentViewSet.as_view({'post': 'resolve_appointment'})),
]