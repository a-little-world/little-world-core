from django.urls import path
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from management.api.user_advanced import AdvancedUserSerializer
from management.api.utils_advanced import filterset_schema_dict
from management.helpers import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.pre_matching_appointment import PreMatchingAppointment
from management.models.state import State
from management.models.user import User
from management.permissions import ManagementPermission


class PreMatchingAppointmentAdvancedSerializer(serializers.ModelSerializer):
    class Meta:
        model = PreMatchingAppointment
        fields = ["uuid", "start_time", "end_time", "created", "user"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        user = instance.user

        representation["user"] = AdvancedUserSerializer(user).data
        representation["is_onboarded"] = user.state.is_onboarded

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
    serializer_class = PreMatchingAppointmentAdvancedSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def get_queryset(self):
        user = self.request.user

        if user.is_staff:
            return PreMatchingAppointment.objects.all()
        elif user.has_perm(ManagementPermission.MATCHING_USER):
            return PreMatchingAppointment.objects.filter(user__in=user.managed_users_queryset(active_only=False))

    def check_management_user_access(self, appointment, request):
        user = appointment.user

        if not request.user.is_staff and not request.user.has_perm(ManagementPermission.MATCHING_USER):
            return False, Response(
                {"msg": "You are not allowed to access this user!"}, status=status.HTTP_401_UNAUTHORIZED
            )

        if not request.user.is_staff and not request.user.has_management_access(user):
            return False, Response(
                {"msg": "You are not allowed to access this user!"}, status=status.HTTP_401_UNAUTHORIZED
            )
        return True, None

    def check_management_user_access_for_user(self, user, request):
        if not request.user.is_staff and not request.user.has_perm(ManagementPermission.MATCHING_USER):
            return False, Response(
                {"msg": "You are not allowed to access this user!"}, status=status.HTTP_401_UNAUTHORIZED
            )

        if not request.user.is_staff and not request.user.has_management_access(user):
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
        responses={201: PreMatchingAppointmentAdvancedSerializer},
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


@extend_schema(
    request=inline_serializer(
        name="MarkPrematchingCallsCompletedRequest",
        fields={
            "appointment_date": serializers.DateTimeField(),
            "selected_users": serializers.ListField(child=serializers.IntegerField()),
            "send_emails_now": serializers.BooleanField(default=False),
        },
    )
)
@api_view(["POST"])
@permission_classes([IsAdminOrMatchingUser])
def mark_prematching_calls_completed(request):
    appointment_date = request.data.get("appointment_date")
    userlist = request.data.get("selected_users")
    send_emails_now = bool(request.data.get("send_emails_now", False))

    try:
        appointment_date = parse_datetime(appointment_date)
    except ValueError:
        return Response(
            {"error": "appointment_date has the wrong format. Use YYYY-MM-DDTHH:MM:SSZ"},
            status=400,
        )

    if appointment_date is None or userlist is None:
        return Response({"error": "appointment_date and userlist are required"}, status=400)

    appointments = PreMatchingAppointment.objects.filter(start_time=appointment_date).select_related("user")
    if appointments is None or len(appointments) == 0:
        return Response(
            {"error": "appointment not found"},
            status=404,
        )

    appointment_users = [appointment.user.id for appointment in appointments if appointment.user is not None]

    user_list_objects = []
    unretrievable_user_ids = []
    for user_id in userlist:
        if user_id not in appointment_users:
            unretrievable_user_ids.append(user_id)
            continue
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            unretrievable_user_ids.append(user_id)
            continue
        if (
            not request.user.is_staff
            and request.user.has_perm(ManagementPermission.MATCHING_USER)
            and not request.user.has_management_access(user)
        ):
            return Response(
                {"error": "You are not allowed to access one or many users for this appointment!"},
                status=401,
            )
        user_list_objects.append(user)

    attended_users = []
    not_attended_users = []
    now = timezone.now()

    for user in user_list_objects:
        previously_onboarded = bool(user.state.is_onboarded)
        user.state.had_prematching_call = True
        user.state.is_onboarded = True
        user.grant_permission(ManagementPermission.USE_RANDOM_CALLS)
        user.state.searching_state = State.SearchingStateChoices.SEARCHING
        user.state.last_prematching_checkoff_at = now
        if not previously_onboarded:
            user.state.onboarding_call_completed_at = appointment_date
        user.state.save()
        attended_users.append(user)

        if not previously_onboarded:
            user.state.attended_auto_email_u071_send = False
            user.state.attended_auto_email_u071_send_at = None
            user.state.save()

    not_attended_appointment_users = list(set(appointment_users) - set(userlist))
    for user_id in not_attended_appointment_users:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            unretrievable_user_ids.append(user_id)
            continue
        if user.state.is_onboarded:
            continue
        user.state.is_onboarded = False
        user.state.last_prematching_checkoff_at = now
        user.state.last_prematching_call_not_attended = True
        user.state.last_not_attended_prematching_call_at = appointment_date

        user.state.not_attended_auto_email_u051_send = False
        user.state.not_attended_auto_email_u051_send_at = None
        user.state.save()
        not_attended_users.append(user)

    message_report = (
        f"Prematching Call Manually marked by {request.user}\n"
        f"Prematching Call Report - {appointment_date.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Attended: {len(attended_users)}\n"
        f"Not attended: {len(not_attended_users)}\n"
        f"Unretrievable users: {len(unretrievable_user_ids)}\n"
        f"Total: {len(appointments)}"
    )

    from management.tasks import slack_notify_communication_channel_async, slack_notify_security_channel_async

    slack_notify_communication_channel_async.delay(message=message_report)
    slack_notify_security_channel_async.delay(message=message_report)
    send_task_id = None
    if send_emails_now:
        from management.tasks import automatic_emails_u051_u071

        send_task = automatic_emails_u051_u071.delay()
        send_task_id = send_task.id

    return Response(
        {
            "success": True,
            "message_report": message_report,
            "unretrievable_user_ids": unretrievable_user_ids,
            "send_emails_now": send_emails_now,
            "send_task_id": send_task_id,
        }
    )


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
    path(
        "api/matching/prematchingappointments/complete_prematching_call/",
        mark_prematching_calls_completed,
    ),
    path("api/matching/prematchingappointments/<pk>/", PreMatchingAppointmentViewSet.as_view({"get": "retrieve"})),
    path(
        "api/matching/prematchingappointments/<pk>/resolve/",
        PreMatchingAppointmentViewSet.as_view({"post": "resolve_appointment"}),
    ),
]
