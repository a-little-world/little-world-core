from rest_framework import viewsets, serializers
from django_filters import rest_framework as filters
from rest_framework.decorators import action
from rest_framework.response import Response
from django.urls import path
from django.utils import timezone
from management.models.pre_matching_appointment import PreMatchingAppointment
# get_user_model
from django.contrib.auth import get_user_model
from management.views.matching_panel import DetailedPaginationMixin, IsAdminOrMatchingUser
from drf_spectacular.utils import extend_schema_view, extend_schema, inline_serializer
from management.api.utils_advanced import filterset_schema_dict
import uuid

class PreMatchingAppointmentSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = PreMatchingAppointment
        fields = ['uuid', 'start_time', 'end_time', 'created', 'user']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user = get_user_model().objects.get(id=instance.user.id)
        
        representation['user'] = {
            'id': user.id,
            'hash': user.hash,
            'email': user.email,
        }
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

        return Response({
            "filters": _filters,
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