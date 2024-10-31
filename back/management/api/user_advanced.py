from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets
from django.db.models import Q
from django.conf import settings
from management.controller import delete_user, make_tim_support_user
from management.twilio_handler import _get_client
from emails.models import EmailLog, AdvancedEmailLogSerializer
from emails.mails import get_mail_data_by_name
from django.urls import path
from django_filters import rest_framework as filters
from management.models.scores import TwoUserMatchingScore
from management.models.user import User
from management.helpers import IsAdminOrMatchingUser, DetailedPagination, DetailedPaginationMixin
from management.models.profile import Profile, MinimalProfileSerializer
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from rest_framework import serializers
from drf_spectacular.utils import extend_schema_view, extend_schema, inline_serializer
from management.api.user_advanced_filter_lists import FILTER_LISTS
from management.api.user_data import get_paginated, serialize_proposed_matches, AdvancedUserMatchSerializer
from management.models.matches import Match
from management.api.user_data import get_paginated_format_v2
from management.models.unconfirmed_matches import ProposedMatch
from management.models.state import State, StateSerializer
from management.models.sms import SmsModel, SmsSerializer
from management.models.management_tasks import MangementTask, ManagementTaskSerializer
from chat.models import Message, MessageSerializer, Chat, ChatSerializer
from management.api.scores import score_between_db_update
from management.tasks import matching_algo_v2
from management.api.utils_advanced import filterset_schema_dict

class MicroUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ["id", "email"]
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["profile"] = {
            "first_name": instance.profile.first_name,
            "second_name": instance.profile.second_name,
        }
        return representation

class AdvancedUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["hash", "id", "email", "date_joined", "last_login"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["profile"] = MinimalProfileSerializer(instance.profile).data

        items_per_page = 5
        user = instance
        confirmed_matches = get_paginated(Match.get_confirmed_matches(user), items_per_page, 1)
        confirmed_matches["items"] = AdvancedUserMatchSerializer(confirmed_matches["items"], many=True, context={"user": user, "status": "confirmed"}).data

        unconfirmed_matches = get_paginated(Match.get_unconfirmed_matches(user), items_per_page, 1)
        unconfirmed_matches["items"] = AdvancedUserMatchSerializer(unconfirmed_matches["items"], many=True, context={"user": user, "status": "unconfirmed"}).data

        support_matches = get_paginated(Match.get_support_matches(user), items_per_page, 1)
        support_matches["items"] = AdvancedUserMatchSerializer(support_matches["items"], many=True, context={"user": user, "status": "support"}).data

        proposed_matches = get_paginated(ProposedMatch.get_open_proposals(user), items_per_page, 1)
        proposed_matches["items"] = serialize_proposed_matches(proposed_matches["items"], user)

        representation["matches"] = {"confirmed": confirmed_matches, "unconfirmed": unconfirmed_matches, "support": support_matches, "proposed": proposed_matches}

        representation["state"] = StateSerializer(instance.state).data

        return representation


class AdvancedMatchingScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = TwoUserMatchingScore
        fields = "__all__"

    def to_representation(self, instance):
        representation = super().to_representation(instance)

        assert "user" in self.context
        user = self.context["user"]
        partner = instance.user2 if user == instance.user1 else instance.user1

        markdown_info = ""
        for score in instance.scoring_results:
            markdown_info += f"## Function `{score['score_function']}`\n"
            try:
                markdown_info += f"{score['res']['markdown_info']}\n\n"
            except:
                markdown_info += "No markdown info available\n\n"

        representation["markdown_info"] = markdown_info

        representation["from_usr"] = {"uuid": user.hash, "id": user.id, **AdvancedUserSerializer(user).data}
        representation["to_usr"] = {"uuid": partner.hash, "id": partner.id, **AdvancedUserSerializer(partner).data}
        return representation


class UserFilter(filters.FilterSet):
    profile__user_type = filters.ChoiceFilter(field_name="profile__user_type", choices=Profile.TypeChoices.choices, help_text="Filter for learner or volunteers")
    
    profile__target_group = filters.ChoiceFilter(field_name="profile__target_group", choices=Profile.TargetGroupChoices2.choices, help_text="Filter for target group")
    
    profile__groups = filters.MultipleChoiceFilter(
        field_name="profile__groups",
        choices=Profile.TargetGroupChoices2.choices,
        help_text="Filter for users based on target groups",
        method="filter_groups",
    )

    profile__newsletter_subscribed = filters.BooleanFilter(field_name="profile__newsletter_subscribed", help_text="Filter for users that are subscribed to the newsletter")

    state__email_authenticated = filters.BooleanFilter(field_name="state__email_authenticated", help_text="Filter for users that have authenticated their email")

    state__had_prematching_call = filters.BooleanFilter(field_name="state__had_prematching_call", help_text="Filter for users that had a prematching call")

    joined_between = filters.DateFromToRangeFilter(field_name="date_joined", help_text="Range filter for when the user joined the platform, accepts string datetimes")

    loggedin_between = filters.DateFromToRangeFilter(field_name="last_login", help_text="Range filter for when the user last logged in, accepts string datetimes")

    state__company = filters.ChoiceFilter(field_name="state__company", choices=[("null", None), ("accenture", "accenture")], help_text="Filter for users that are part of a company")

    list = filters.ChoiceFilter(field_name="list", choices=[(entry.name, entry.description) for entry in FILTER_LISTS], method="filter_list", help_text="Filter for users that are part of a list")

    order_by = filters.OrderingFilter(
        fields=(
            ("date_joined", "date_joined"),
            ("last_login", "last_login"),
            ("id", "id"),
            ("email", "email"),
        ),
        help_text="Order by field",
    )

    search = filters.CharFilter(method="filter_search", label="Search")

    def filter_search(self, queryset, name, value):
        return queryset.filter(Q(hash__icontains=value) | Q(profile__first_name__icontains=value) | Q(profile__second_name__icontains=value) | Q(email__icontains=value))

    def filter_list(self, queryset, name, value):
        selected_filter = next(filter(lambda entry: entry.name == value, FILTER_LISTS))
        if selected_filter.queryset:
            return selected_filter.queryset(queryset)
        else:
            return queryset
        
    def filter_groups(self, queryset, name, value):
        if value:
            query = Q()
            for item in value:
                query |= Q(**{f"{name}__icontains": item})
            return queryset.filter(query)
        return queryset

    class Meta:
        model = User
        fields = ["hash", "id", "email"]


@extend_schema_view(
    list=extend_schema(summary="List users"),
    retrieve=extend_schema(summary="Retrieve user"),
)
class AdvancedUserViewset(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-date_joined")

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = UserFilter

    serializer_class = AdvancedUserSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]

    def get_queryset(self):
        is_staff = self.request.user.is_staff
        if is_staff:
            return User.objects.all()
        else:
            return User.objects.filter(id__in=self.request.user.state.managed_users.all(), is_active=True)

    @action(detail=False, methods=["get"])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # 1 - retrieve all the filters
        filterset = self.filterset_class()
        _filters = filterset_schema_dict(filterset, include_lookup_expr, "/api/matching/users/", request)
        return Response({"filters": _filters, "lists": [entry.to_dict() for entry in FILTER_LISTS]})

    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            return super().get_object()
        else:
            # The two alternate lookup options are email & hash
            # So lets check if there is an '@' in the string
            is_email = "@" in self.kwargs["pk"]
            if is_email:
                return super().get_queryset().get(email=self.kwargs["pk"])
            else:
                return super().get_queryset().get(hash=self.kwargs["pk"])

    @action(detail=True, methods=["get"])
    def scores(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        matching_scores = TwoUserMatchingScore.get_matching_scores(obj).order_by("-score")
        paginator = DetailedPagination()
        pages = paginator.get_paginated_response(paginator.paginate_queryset(matching_scores, request)).data
        pages["results"] = AdvancedMatchingScoreSerializer(pages["results"], many=True, context={"user": obj}).data
        return Response(pages)

    @action(detail=True, methods=["get"])
    def prematching_appointment(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        latest_appointment = PreMatchingAppointment.objects.filter(user=obj).order_by("-created").first()
        return Response(PreMatchingAppointmentSerializer(latest_appointment, many=False).data)

    @extend_schema(request=inline_serializer(name="ScoreBetweenRequest", fields={"to_user": serializers.IntegerField()}))
    @action(detail=True, methods=["post"])
    def score_between(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        from_usr = obj
        to_usr = request.data["to_user"]
        to_usr = User.objects.get(id=to_usr)
        matching_score = TwoUserMatchingScore.get_score(from_usr, to_usr)
        if matching_score is None:
            total_score, matchable, results, score = score_between_db_update(from_usr, to_usr)
            matching_score = score

        score = AdvancedMatchingScoreSerializer(matching_score, context={"user": from_usr}).data
        return Response(score)

    def check_management_user_access(self, user, request):
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)

        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=user.pk).exists():
            return False, Response({"msg": "You are not allowed to access this user!"}, status=401)
        return True, None

    @extend_schema(request=inline_serializer(name="MarkReadMessageRequest", fields={"message_id": serializers.CharField()}))
    @action(detail=True, methods=["post"])
    def message_mark_read(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        message_id = request.data["message_id"]

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        message = Message.objects.get(uuid=message_id)
        message.read = True
        message.save()

        return Response({"msg": "Message marked as read"})

    @extend_schema(request=inline_serializer(name="DeleteMessageRequest", fields={"message_id": serializers.CharField()}))
    @action(detail=True, methods=["post"])
    def delete_message(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        message_id = request.data["message_id"]

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        message = Message.objects.get(uuid=message_id)
        message.delete()

        return Response({"msg": "Message deleted"})

    @extend_schema(
        request=inline_serializer(
            name="MessagesGetRequest",
            # description='If match_uuid is provided, the chat of the match is returned, otherwise the support user chat',
            fields={"match_uuid": serializers.CharField(required=False)},
        )
    )
    @action(detail=True, methods=["get"])
    def messages(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        # If not match_uuid is provided per default returns the support user chat
        match_uuid = request.query_params.get("match_uuid", None)

        censor_messages = True
        if match_uuid is not None:
            matching = Match.objects.filter(
                Q(user1=obj) | Q(user2=obj),
                uuid=match_uuid,
            ).first()
        else:
            censor_messages = False
            support_matching = Match.objects.filter(Q(user1=obj) | Q(user2=obj), support_matching=True).first()
            matching = support_matching

        partner = matching.get_partner(obj)
        chat = Chat.objects.filter(Q(u1=obj, u2=partner) | Q(u1=partner, u2=obj)).first()

        page = request.query_params.get("page", 1)
        page_size = request.query_params.get("page_size", 10)

        messages_qs = chat.get_messages()

        messages = get_paginated_format_v2(messages_qs, page_size, page)
        messages["results"] = MessageSerializer(messages["results"], many=True, context={"censor_text": censor_messages}).data

        return Response({"chat": ChatSerializer(chat).data, "messages": messages})

    @extend_schema(request=inline_serializer(name="SmsRequest", fields={"message": serializers.CharField()}))
    @action(detail=True, methods=["get", "post"])
    def sms(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        if request.method == "POST":
            sms = SmsModel.objects.create(recipient=obj, send_initator=request.user, message=request.data["message"])
            client = _get_client()
            response = client.messages.create(body=request.data["message"], from_=settings.TWILIO_SMS_NUMBER, to=obj.profile.phone_mobile)

            sms.twilio_response = response.__dict__
            sms.save()
            return Response(SmsSerializer(sms).data)
        else:
            sms = SmsModel.objects.filter(recipient=obj).order_by("-created_at")

            return Response(SmsSerializer(sms, many=True).data)

    @action(detail=True, methods=["post"])
    def message_reply(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        message = obj.message(request.data["message"], sender=request.user)

        serialized = MessageSerializer(message).data

        return Response(serialized)

    @action(detail=True, methods=["get", "post"])
    def tasks(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        if request.method == "POST":
            task = MangementTask.create_task(obj, request.data["description"], request.user)
            return Response(ManagementTaskSerializer(task).data)

        tasks = MangementTask.objects.filter(user=obj, state=MangementTask.MangementTaskStates.OPEN)

        return Response(ManagementTaskSerializer(tasks, many=True).data)

    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()
        _os = obj.state

        if request.method == "POST":
            _os.notes = request.data["notes"]
            _os.save()
            return Response(_os.notes)
        else:
            if not _os.notes:
                _os.notes = ""
                _os.save()
            return Response(_os.notes)

    @extend_schema(request=inline_serializer(name="MarkUnresponsiveRequest", fields={"unresponsive": serializers.BooleanField(default=True)}))
    @action(detail=True, methods=["post"])
    def mark_unresponsive(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        obj.state.unresponsive = request.data.get("unresponsive", True)
        obj.state.save()
        return Response({"success": True})

    @extend_schema(request=inline_serializer(name="ChangeNewsletterSubscribed", fields={"newsletter_subscribed": serializers.BooleanField(default=False)}))
    @action(detail=True, methods=["post"])
    def change_newsletter_subscribed(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        obj.profile.newsletter_subscribed = request.data.get("newsletter_subscribed", False)
        obj.profile.save()
        return Response({"success": True})

    @extend_schema(request=inline_serializer(name="MarkPrematchingCallCompletedRequest", fields={"had_prematching_call": serializers.BooleanField(default=True)}))
    @action(detail=True, methods=["post"])
    def mark_prematching_call_completed(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        obj.state.had_prematching_call = request.data.get("had_prematching_call", True)
        obj.state.save()
        return Response({"success": True})

    @action(detail=True, methods=["get"])
    def request_score_update(self, request, pk=None):
        consider_within_days = int(request.query_params.get("days_searching", 60))

        task = matching_algo_v2.delay(pk, consider_within_days)
        return Response({"task_id": task.id})

    @extend_schema(request=inline_serializer(name="CompleteTaskRequest", fields={"task_id": serializers.CharField()}))
    @action(detail=False, methods=["post"])
    def complete_task(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        task = MangementTask.objects.get(pk=request.data["task_id"], user=obj)
        task.state = MangementTask.MangementTaskStates.FINISHED
        task.save()
        return Response(ManagementTaskSerializer(task).data)

    @extend_schema(request=inline_serializer(name="DeleteUserRequest", fields={"send_deletion_email": serializers.BooleanField(default=False)}))
    @action(detail=True, methods=["post"])
    def delte_user(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        if obj.is_staff or obj.is_superuser:
            return Response({"msg": "You can't delete a staff or superuser!"}, status=401)

        if obj.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({"msg": "You can't delete a matching user!"}, status=401)

        delete_user(obj, request.user, self.request.data.get("send_deletion_email", False))
        return Response({"msg": "User deleted"})

    @extend_schema(request=inline_serializer(name="ChangeSearchingStateRequest", fields={"searching_state": serializers.ChoiceField(choices=State.MatchingStateChoices.choices, default=State.MatchingStateChoices.IDLE)}))
    @action(detail=True, methods=["post"])
    def change_searching_state(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        obj.state.matching_state = request.data.get("searching_state", State.MatchingStateChoices.IDLE)
        obj.state.save()

        return Response({"msg": "State changed"})

    @extend_schema(request=inline_serializer(name="MakeTimSupportRequest", fields={"old_management_mail": serializers.CharField(default="littleworld.management@gmail.com"), "send_new_management_message": serializers.BooleanField(default=True), "message": serializers.CharField(required=False)}))
    @action(detail=True, methods=["post"])
    def make_tim_support(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        # Here we skip the acess check logicly... ( at some point this api has to be replaced with a more secure procedure )

        make_tim_support_user(obj, old_management_mail=request.data.get("old_management_mail", "littleworld.management@gmail.com"), send_message=request.data.get("send_new_management_message", True), custom_message=request.data.get("message", None))
        return Response({"msg": "User is now a TIM support user"})

    @action(detail=True, methods=["get"])
    def emails(self, request, pk=None):
        self.kwargs["pk"] = pk
        obj = self.get_object()

        has_access, res = self.check_management_user_access(obj, request)
        if not has_access:
            return res

        page = request.query_params.get("page", 1)
        page_size = request.query_params.get("page_size", 10)

        email_logs = get_paginated_format_v2(EmailLog.objects.filter(receiver=obj), page_size, page)
        email_logs["results"] = AdvancedEmailLogSerializer(email_logs["results"], many=True).data

        return Response(email_logs)
    
    @action(detail=False, methods=["get"])
    def export(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = MicroUserSerializer(queryset, many=True)

        return Response(serializer.data)


viewset_actions = [
    path("api/matching/users_export/", AdvancedUserViewset.as_view({"get": "export"})),
    path("api/matching/users/<pk>/scores/", AdvancedUserViewset.as_view({"get": "scores"})),
    path("api/matching/users/<pk>/prematching_appointment/", AdvancedUserViewset.as_view({"get": "prematching_appointment"})),
    path("api/matching/users/<pk>/score_between/", AdvancedUserViewset.as_view({"post": "score_between"})),
    path("api/matching/users/<pk>/message_mark_read/", AdvancedUserViewset.as_view({"post": "message_mark_read"})),
    path("api/matching/users/<pk>/messages/", AdvancedUserViewset.as_view({"get": "messages"})),
    path("api/matching/users/<pk>/sms/", AdvancedUserViewset.as_view({"get": "sms", "post": "sms"})),
    path("api/matching/users/<pk>/message_reply/", AdvancedUserViewset.as_view({"post": "message_reply"})),
    path("api/matching/users/<pk>/tasks/", AdvancedUserViewset.as_view({"get": "tasks", "post": "tasks"})),
    path("api/matching/users/<pk>/notes/", AdvancedUserViewset.as_view({"get": "notes", "post": "notes"})),
    path("api/matching/users/<pk>/delete_message/", AdvancedUserViewset.as_view({"get": "delete_message"})),
    path("api/matching/users/<pk>/request_score_update/", AdvancedUserViewset.as_view({"get": "request_score_update"})),
    path("api/matching/users/<pk>/complete_task/", AdvancedUserViewset.as_view({"post": "complete_task"})),
    path("api/matching/users/<pk>/mark_unresponsive/", AdvancedUserViewset.as_view({"post": "mark_unresponsive"})),
    path("api/matching/users/<pk>/mark_prematching_call_completed/", AdvancedUserViewset.as_view({"post": "mark_prematching_call_completed"})),
    path("api/matching/users/<pk>/delete_user/", AdvancedUserViewset.as_view({"post": "delte_user"})),
    path("api/matching/users/<pk>/change_searching_state/", AdvancedUserViewset.as_view({"post": "change_searching_state"})),
    path("api/matching/users/<pk>/make_tim_support/", AdvancedUserViewset.as_view({"post": "make_tim_support"})),
    path("api/matching/users/<pk>/emails/", AdvancedUserViewset.as_view({"get": "emails"})),
    path("api/matching/users/<pk>/change_newsletter_subscribed/", AdvancedUserViewset.as_view({"post": "change_newsletter_subscribed"})),
]

api_urls = [path("api/matching/users/", AdvancedUserViewset.as_view({"get": "list"})), path("api/matching/users/filters/", AdvancedUserViewset.as_view({"get": "get_filter_schema"})), path("api/matching/users/<pk>/", AdvancedUserViewset.as_view({"get": "retrieve"})), *viewset_actions]
