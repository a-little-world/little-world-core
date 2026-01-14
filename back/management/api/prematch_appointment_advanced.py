from django.urls import path
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from management.api.user_advanced import AdvancedUserSerializer
from management.api.utils_advanced import filterset_schema_dict
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.pre_matching_appointment import PreMatchingAppointment


class PreMatchingAppointmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreMatchingAppointment
        fields = ["uuid", "start_time", "end_time", "created", "user"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user = instance.user

        representation["user"] = AdvancedUserSerializer(user).data
        representation["had_prematching_call"] = user.state.had_prematching_call

        return representation


class PreMatchingAppointmentFilter(filters.FilterSet):
    start_time = filters.DateFromToRangeFilter(field_name="start_time", help_text="Range filter for start time")

    end_time = filters.DateFromToRangeFilter(field_name="end_time", help_text="Range filter for end time")

    list = filters.DateTimeFilter(
        field_name="start_time",
    )

    order_by = filters.OrderingFilter(
        fields=(
            ("start_time", "start_time"),
            ("end_time", "end_time"),
        ),
        help_text="Ordering filter for appointments",
    )

    class Meta:
        model = PreMatchingAppointment
        fields = ["start_time", "end_time", "user"]


@extend_schema_view(
    list=extend_schema(summary="List PreMatchingAppointments"),
    retrieve=extend_schema(summary="Retrieve PreMatchingAppointment"),
)
class PreMatchingAppointmentViewSet(viewsets.ModelViewSet):
    queryset = PreMatchingAppointment.objects.all().order_by("-created")
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

        if not request.user.is_staff and not request.user.state.has_extra_user_permission(
            State.ExtraUserPermissionChoices.MATCHING_USER
        ):
            return False, Response(
                {"msg": "You are not allowed to access this user!"}, status=status.HTTP_401_UNAUTHORIZED
            )

        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=user.pk).exists():
            return False, Response(
                {"msg": "You are not allowed to access this user!"}, status=status.HTTP_401_UNAUTHORIZED
            )
        return True, None

    def check_management_user_access_for_user(self, user, request):
        from management.models.state import State

        if not request.user.is_staff and not request.user.state.has_extra_user_permission(
            State.ExtraUserPermissionChoices.MATCHING_USER
        ):
            return False, Response(
                {"msg": "You are not allowed to access this user!"}, status=status.HTTP_401_UNAUTHORIZED
            )

        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=user.pk).exists():
            return False, Response(
                {"msg": "You are not allowed to access this user!"}, status=status.HTTP_401_UNAUTHORIZED
            )

        return True, None

    @action(detail=False, methods=["get"])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # Retrieve all the filters
        filterset = self.filterset_class()
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/prematchingappointments/", request)

        # Here we actally generate the filter list dynamicly.
        # We start of by grouping the together the 10 most recent start_times

        top_x = 40
        start_times = (
            PreMatchingAppointment.objects.all()
            .order_by("-start_time")
            .values_list("start_time", flat=True)
            .distinct()[:top_x]
        )
        from management.api.user_advanced_filter_lists import FilterListEntry

        filter_lists = []
        for start_time in start_times:
            filter_lists.append(
                FilterListEntry(
                    name=str(start_time),
                    description=str(start_time),
                    queryset=lambda qs: qs.filter(start_time=start_time),
                ).to_dict()
            )

        return Response({"filters": _filters, "lists": filter_lists})

    @extend_schema(
        summary="Resolve an appointment",
        request=inline_serializer(
            name="ResolveAppointmentRequest",
            fields={
                "appointment_uuid": serializers.UUIDField(),
            },
        ),
    )
    @action(detail=True, methods=["post"])
    def resolve_appointment(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        # Implement your resolve logic here
        return Response({"msg": "Appointment resolved"})

    @extend_schema(
        summary="Create an appointment for a user at a specific date",
        request=inline_serializer(
            name="CreateAppointmentForUserRequest",
            fields={
                "user_id": serializers.IntegerField(),
                "start_time": serializers.DateTimeField(),
                "end_time": serializers.DateTimeField(required=False),
            },
        ),
        responses={201: PreMatchingAppointmentSerializer},
    )
    @action(detail=False, methods=["post"])
    def create_appointment_for_user(self, request):
        """
        Create a pre-matching appointment for a specific user at a given start time.
        If ``end_time`` is not provided it will default to one hour after ``start_time``.
        """
        from datetime import timedelta

        from django.utils import timezone
        from django.utils.dateparse import parse_datetime

        from management.models.user import User

        user_id = request.data.get("user_id")
        start_time_raw = request.data.get("start_time")
        end_time_raw = request.data.get("end_time")

        if user_id is None or start_time_raw is None:
            return Response(
                {"error": "user_id and start_time are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        has_access, res = self.check_management_user_access_for_user(user, request)
        if not has_access:
            return res

        # Parse datetimes
        start_time = parse_datetime(start_time_raw) if isinstance(start_time_raw, str) else start_time_raw
        if start_time is None:
            return Response(
                {"error": "start_time has the wrong format. Use YYYY-MM-DDTHH:MM:SSZ"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if end_time_raw:
            end_time = parse_datetime(end_time_raw) if isinstance(end_time_raw, str) else end_time_raw
            if end_time is None:
                return Response(
                    {"error": "end_time has the wrong format. Use YYYY-MM-DDTHH:MM:SSZ"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            end_time = start_time + timedelta(hours=1)

        # Ensure datetimes are timezone-aware
        if timezone.is_naive(start_time):
            start_time = timezone.make_aware(start_time, timezone.get_current_timezone())
        if timezone.is_naive(end_time):
            end_time = timezone.make_aware(end_time, timezone.get_current_timezone())

        appointment = PreMatchingAppointment.objects.create(
            user=user,
            start_time=start_time,
            end_time=end_time,
        )

        serializer = self.get_serializer(appointment)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            return super().get_object()
        else:
            return super().get_queryset().get(uuid=self.kwargs["pk"])


api_urls = [
    path("api/matching/prematchingappointments/", PreMatchingAppointmentViewSet.as_view({"get": "list"})),
    path(
        "api/matching/prematchingappointments/filters/",
        PreMatchingAppointmentViewSet.as_view({"get": "get_filter_schema"}),
    ),
    path(
        "api/matching/prematchingappointments/create_appointment_for_user/",
        PreMatchingAppointmentViewSet.as_view({"post": "create_appointment_for_user"}),
    ),
    path("api/matching/prematchingappointments/<pk>/", PreMatchingAppointmentViewSet.as_view({"get": "retrieve"})),
    path(
        "api/matching/prematchingappointments/<pk>/resolve/",
        PreMatchingAppointmentViewSet.as_view({"post": "resolve_appointment"}),
    ),
]
