from django.contrib.auth.decorators import user_passes_test
from django.utils import timezone
from datetime import timedelta, datetime
from rest_framework import viewsets, serializers
from rest_framework.permissions import IsAdminUser, BasePermission
from django.core.paginator import Paginator
from management.models.matches import Match
from management.models.sms import SmsModel, SmsSerializer
from management.models.management_tasks import MangementTask, ManagementTaskSerializer
from rest_framework.decorators import action
from django.shortcuts import render
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from chat.models import Chat, Message, ChatSerializer, MessageSerializer

from management.models.unconfirmed_matches import UnconfirmedMatch
from management.models.scores import TwoUserMatchingScore
from management.api.scores import score_between_db_update
from management import controller
from enum import Enum
import json
from management.models.user import (
    User,
)

from management.models.profile import (
    Profile,
    ProfileSerializer,
    ProposalProfileSerializer,
)

from management.models.state import (
    StateSerializer,
    State
)
from typing import OrderedDict
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.utils import serializer_helpers
from django.db.models import Q
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiExample
from rest_framework import serializers

class IsAdminOrMatchingUser(BasePermission):
    """
    Allows access only to admin users.
    """

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_staff) or \
            bool(request.user and request.user.is_authenticated and request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER))
            
class IfMatchingUserHasPkPermission(BasePermission):
    # Checks if that manageing user is allowed to access user info for the user that he is trying to access
    
    def has_permission(self, request, view):
        
        if request.user.is_staff:
            return True
        if request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            if not "pk" in view.kwargs:
                return False
            return request.user.state.managed_users.filter(pk=view.kwargs["pk"]).exists()
        return False


def serialize_proposed_matches(matching_proposals, user):
    serialized = []
    for proposal in matching_proposals:
        
        partner = proposal.get_partner(user)
        serialized.append({
            "id": str(proposal.hash), # TODO: rename
            "partner": {
                "id": str(partner.hash),
                **ProposalProfileSerializer(partner.profile).data
            } # TODO: this want some additional fields
        })
        
    return serialized

def serialize_matches(matches, user):
    serialized = []
    for match in matches:
        
        partner = match.get_partner(user)
        serialized.append({
            "id": str(match.uuid),
            "partner": {
                **ProfileSerializer(partner.profile).data,
                "id": str(partner.pk),
            }
        })
        
    return serialized

def get_paginated(query_set, items_per_page, page):
    pages = Paginator(query_set, items_per_page).page(page)
    return {
        "items": list(pages),
        "totalItems": pages.paginator.count,
        "itemsPerPage": items_per_page,
        "currentPage": page,
    }
    
ADMIN_USER_MATCH_ITEMS = 5

class AugmentedPagination(PageNumberPagination):
    page_size = 10
    max_page_size = 10
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
            ('page' , self.page.number),
            ('next', self.get_next_link()),
            ('previous', self.get_previous_link()),
            ('results', data), # The  following are extras added by me:
            ('page_size', self.page_size),
            ('next_page', self.page.next_page_number() if self.page.has_next() else None),
            ('previous_page', self.page.previous_page_number() if self.page.has_previous() else None),
            ('last_page', self.page.paginator.num_pages),
            ('first_page', 1),
        ]))

class DetailedPaginationMixin(AugmentedPagination):
    pass

class AdminViewSetExtensionMixin:
    
    @classmethod
    def emulate(cls, request, **kwargs):
        obj = cls()
        obj.request = request
        obj.format_kwarg = None
        
        def pop_data(function) -> dict:
            def wrapper(*args, **kwargs):
                kwargs['request'] = request
                return function(*args, **kwargs).data
            return wrapper
        
        POP_FUNCS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]
        for func in POP_FUNCS:
            if hasattr(obj, func):
                setattr(obj, func, pop_data(getattr(obj, func)))
        return obj

    def get_permissions(self):
        
        # TODO: non staff users must be users with the 'matching' permission
        permission_classes = [IsAdminOrMatchingUser, IfMatchingUserHasPkPermission]

        return [permission() for permission in permission_classes]
    
    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            # assume uuid
            return super().get_object()
        else:
            return super().get_queryset().get(hash=self.kwargs["pk"])
        
def update_representation(representation, instance):
    representation['profile'] = ProfileSerializer(instance.profile).data
    representation['state'] = StateSerializer(instance.state).data
    
    user = instance
    items_per_page = ADMIN_USER_MATCH_ITEMS

    confirmed_matches = get_paginated(Match.get_confirmed_matches(user), items_per_page, 1)
    confirmed_matches["items"] = serialize_matches(confirmed_matches["items"], user)
    
    #print("confirmed matches", [f'{i["partner"]["id"]} m_id {i["id"]}' for i in confirmed_matches["items"]])

    unconfirmed_matches = get_paginated(Match.get_unconfirmed_matches(user), items_per_page, 1)
    unconfirmed_matches["items"] = serialize_matches(unconfirmed_matches["items"], user)

    #print("unconfirmed matches", [f'{i["partner"]["id"]} m_id {i["id"]}' for i in unconfirmed_matches["items"]])

    support_matches = get_paginated(Match.get_support_matches(user), items_per_page, 1)
    support_matches["items"] = serialize_matches(support_matches["items"], user)
    
    proposed_matches = get_paginated(UnconfirmedMatch.get_open_proposals(user), items_per_page, 1)
    proposed_matches["items"] = serialize_proposed_matches(proposed_matches["items"], user)
    
    representation['matches'] = {
        "confirmed": confirmed_matches,
        "unconfirmed": unconfirmed_matches,
        "support": support_matches,
        "proposed": proposed_matches
    }
    return representation

class AdminUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['hash', 'id', 'email', 'date_joined', 'last_login']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        
        return update_representation(representation, instance)
    
def serialize_messages_for_matching(instance, representation, censor_messages=True):

    def get_messages(match):
        partner = controller.get_user_by_pk(match['partner']['id'])
        print("TBS", partner, instance)

        _msgs = Message.objects.filter(
            Q(sender=partner, recipient=instance) | Q(sender=instance, recipient=partner)
        ).order_by("-created")
        messages = get_paginated(_msgs, 10, 1)
        
        
        if not Chat.get_chat([instance, partner]):
            messages["no_dialog"] = True # prop means it has been deleted
        return messages
    
    confirmed = representation['matches']['confirmed']['items']
    support = representation['matches']['support']['items']
    unconfirmed = representation['matches']['unconfirmed']['items']
    
    def update_messages(match, messages, censor=True):
        print("TBS", match["partner"]["id"], match["partner"]["first_name"])
        partner = controller.get_user_by_pk(match['partner']['id'])
        print("PARTNER", partner)
        _msg = get_messages(match)
        if _msg is None:
            return messages
        messages[match['id']] = _msg
        messages[match['id']]["match"] = {
            "match_id": match['id'],
            "profile": match['partner'],
            "state": StateSerializer(partner.state).data,
            "with_management": True if match in support else False
        }
        messages[match['id']]["items"] = reversed([MessageSerializer(item).data for item in _msg["items"]])
        if censor:
            messages[match['id']]["items"] = [{**i, "text": "CENSORED"} for i in messages[match['id']]["items"]]
        return messages
    
    messages = {}
    for match in [*confirmed, *unconfirmed]:
        messages = update_messages(match, messages, censor=censor_messages)
        
        
    for match in [*support]:
        messages = update_messages(match, messages, censor=False)
        
    return messages
    
class AdvancedAdminUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['hash', 'id', 'email', 'date_joined', 'last_login']
    
    def to_representation(self, instance):
        from emails.models import EmailLog, EmailLogSerializer, AdvancedEmailLogSerializer
        print("SERIALIZING", instance)
        representation = super().to_representation(instance)
        representation = update_representation(representation, instance)
        
        
        censor_messages = True
        if ('request' in self.context) and self.context['request'].user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.UNCENSORED_ADMIN_MATCHER):
            censor_messages = False
        
        # Now also add the matches messages
        # And the chat with that user
        include_messages = False
        if ('request' in self.context) and self.context['request'].query_params.get('messages', False) == "include":
            include_messages = True
        if ('messages' in self.context) and self.context['messages']:
            include_messages = True
        
        if include_messages:    
            representation['messages'] = serialize_messages_for_matching(instance, representation, censor_messages=censor_messages)

        # Also get the email logs
        email_logs = get_paginated(EmailLog.objects.filter(receiver=instance), 10, 1)
        email_logs["items"] = AdvancedEmailLogSerializer(email_logs["items"], many=True).data
        
        representation['email_logs'] = email_logs
        
        return representation
            


class AdminUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdminUserSerializer 
    
def make_user_viewset(_queryset, _serializer_class=AdminUserSerializer, items_per_page=ADMIN_USER_MATCH_ITEMS):

    class Pagination(AugmentedPagination):
        page_size = items_per_page
        max_page_size = items_per_page

    class __EmulatedUserViewset(AdminViewSetExtensionMixin, viewsets.ModelViewSet):
        queryset = _queryset
        serializer_class = _serializer_class
        pagination_class = Pagination
    return __EmulatedUserViewset


    
class QuerySetEnum(Enum):
    all = "All users ordered by date joined!"
    searching = "Users who are searching for a match! Exlude users that have not finished the user form or verified their email!"
    needs_matching = "All users in 'searching' without any user that has a open poposal!"
    in_registration = "Users who have not finished the user form or verified their email!"
    active_within_3weeks = "Users who have been active within the last 3 weeks!"
    active_match = "Users who have communicated with their match in the last 4 weeks"
    highquality_matching = "Users who have at least one matching with 20+ Messages"
    message_reply_required = "Users who have a unread message to the admin user"
    read_message_but_not_replied = "Read messages to the management user that have not been replied to"
    users_with_open_tasks = "Users who have open tasks"
    users_with_open_proposals = "Users who have open proposals"
    users_require_prematching_call_not_booked = "Users that still require a pre-matching call before matching, but haven't booked one yet"
    users_with_booked_prematching_call = "Users that have booked a pre-matching call"
    users_with_booked_prematching_call_exculde_had = "Users that have booked a pre-matching call but have not had one yet"
    
    def as_dict():
        return {i.name: i.value for i in QuerySetEnum}
    
def three_weeks_ago():
    return datetime.now() - timedelta(weeks=3)

def get_user_with_message_to_admin():
    # TODO: in the future each staff mover has to be filtered here individually
    
    from django.db.models import Subquery, OuterRef, Count
    admin = controller.get_base_management_user()
    unread_messages = Message.objects.filter(
        recipient=admin,
        read=False
    ).order_by('created')
    unread_senders_ids = unread_messages.values("sender")
    sender_users = User.objects.filter(id__in=Subquery(unread_senders_ids))
    return sender_users

def get_user_with_message_to_admin_that_are_read_but_not_replied():
    from django.db.models import Subquery, OuterRef, Count, F
    admin_pk = controller.get_base_management_user()

    # All dialogs with the management user
    dialogs_with_the_management_user = Chat.objects.filter(
        Q(u1=admin_pk) | Q(u2=admin_pk)
    )
    
    last_message_per_user = Message.objects.filter(
        # Message was sent by the user and received by the admin
        (Q(sender_id=OuterRef('id'), recipient_id=admin_pk) 
        # OR Message was sent by the admin and received by the user
        | Q(sender_id=admin_pk, recipient_id=OuterRef('id')))
    ).order_by('created').values('created')[:1]

    users_in_dialog_with_management_user = User.objects.annotate(
        # The last message sent by the user or received by the user
        last_message_id=Subquery(last_message_per_user.values('id')[:1])

    ).filter(
        # The last message was sent to the management user AND has been read
        Q(last_message_id__in=Message.objects.filter(sender_id=F('id'), recipient_id=admin_pk, read=True)) 
        # OR The last message was from the management user AND has not been read
        | Q(last_message_id__in=Message.objects.filter(sender_id=admin_pk, recipient_id=F('id'), read=False))
    )

    return users_in_dialog_with_management_user    

def users_with_open_proposals():
    # This has to return a query set of users
    # that have open proposals

    # First we get all the open proposals
    open_proposals = UnconfirmedMatch.objects.filter(closed=False)
    
    # Then we get all the users that have open proposals
    # Basicly wee need all users that are open_proposals[X] .user1 or .user2
    users_with_open_proposals = User.objects.filter(
        Q(pk__in=open_proposals.values("user1")) | 
        Q(pk__in=open_proposals.values("user2"))
    ).distinct().order_by('-date_joined')
    
    return users_with_open_proposals

def get_active_match_query_set():
    # Calculate the date 4 weeks ago from now
    four_weeks_ago = timezone.now() - timedelta(weeks=4)

    # Get distinct users from sender and recipient fields in MessageModel
    senders = Message.objects.filter(created__gte=four_weeks_ago).values_list('sender', flat=True).distinct()


    # Now you have the users who have sent a message within the last 4 weeks
    print(senders)
    return User.objects.filter(pk__in=senders)


def get_quality_match_querry_set():
    
    from django.db.models import Subquery, OuterRef, Count

    # Create a subquery object to annotate the match with msg_count
    sq = Message.objects.filter(
        Q(sender=OuterRef('user1'), recipient=OuterRef('user2')) | 
        Q(sender=OuterRef('user2'), recipient=OuterRef('user1'))
    ).values('sender')

    # Annotate the match with the count of messages
    matches_with_msg_count = Match.objects.filter(active=True).annotate(
        msg_count=Subquery(
            sq.annotate(cnt=Count('id')).values('cnt')[:1]
        )
    )

    # Get the matches where msg_count >= 20
    matches_with_enough_msgs = matches_with_msg_count.filter(msg_count__gte=20)
    # Query Users based on the matches_with_enough_msgs queryset
    filtered_users = User.objects.filter(
        Q(match_user1__in=matches_with_enough_msgs) | 
        Q(match_user2__in=matches_with_enough_msgs)
    ).distinct().order_by('-date_joined')
    return filtered_users

def users_with_open_tasks():
    # This has to return a query set of users
    # that have open tasks

    # First we get all the open tasks
    open_tasks = MangementTask.objects.filter(state=MangementTask.MangementTaskStates.OPEN)
    # Then we get all the users that have open tasks
    users_with_open_tasks = User.objects.filter(id__in=open_tasks.values("user"))
    return users_with_open_tasks

def users_that_are_searching_but_have_no_proposal():
    unconfirmed_matches = UnconfirmedMatch.objects.filter(closed=False)
    
    return User.objects.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__had_prematching_call=True, # TODO: filter should only be applied, if require_prematching_call = True
        state__matching_state=State.MatchingStateChoices.SEARCHING
    ).exclude(
        Q(pk__in=unconfirmed_matches.values("user1")) |
        Q(pk__in=unconfirmed_matches.values("user2"))
    ).filter(
        state__unresponsive=False
    ).order_by('-date_joined')

def users_with_booked_prematching_call():
    from management.models.pre_matching_appointment import PreMatchingAppointment

    user_with_prematching_booked = PreMatchingAppointment.objects.all().values("user")

    return User.objects.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__had_prematching_call=False,
        state__unresponsive=False,
        pk__in=user_with_prematching_booked
    ).order_by('-date_joined')


def users_require_prematching_call_not_booked():
    from management.models.pre_matching_appointment import PreMatchingAppointment

    user_with_prematching_booked = PreMatchingAppointment.objects.all().values("user")

    return User.objects.filter(
        state__user_form_state=State.UserFormStateChoices.FILLED,
        state__email_authenticated=True,
        state__matching_state=State.MatchingStateChoices.SEARCHING,
        state__had_prematching_call=False,
        state__unresponsive=False
    ).exclude(
        pk__in=user_with_prematching_booked
    ).order_by('-date_joined')

    


    
def get_QUERY_SETS():
    return {
        QuerySetEnum.all.name: User.objects.all().order_by('-date_joined'),
        QuerySetEnum.searching.name: User.objects.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__had_prematching_call=False,
            state__matching_state=State.MatchingStateChoices.SEARCHING
        ).order_by('-date_joined'),
        QuerySetEnum.needs_matching.name: users_that_are_searching_but_have_no_proposal(),
        QuerySetEnum.in_registration.name: User.objects.filter(
            Q(state__user_form_state=State.UserFormStateChoices.UNFILLED) | Q(state__email_authenticated=False) | Q(state__had_prematching_call=False) ).order_by('-date_joined'),
        QuerySetEnum.active_within_3weeks.name: User.objects.filter(
            last_login__gte=three_weeks_ago()).order_by('-date_joined'),
        QuerySetEnum.active_match.name: get_active_match_query_set(),
        QuerySetEnum.highquality_matching.name: get_quality_match_querry_set(),
        QuerySetEnum.message_reply_required.name: get_user_with_message_to_admin(),
        QuerySetEnum.read_message_but_not_replied.name: get_user_with_message_to_admin_that_are_read_but_not_replied(),
        QuerySetEnum.users_with_open_tasks.name: users_with_open_tasks(),
        QuerySetEnum.users_with_open_proposals.name: users_with_open_proposals(),
        QuerySetEnum.users_require_prematching_call_not_booked.name: users_require_prematching_call_not_booked(),
        QuerySetEnum.users_with_booked_prematching_call.name: users_with_booked_prematching_call(),
    }

def get_staff_queryset(query_set, request):
    # Should be done by checking a condition and then filtering the queryset additionally...
    if request.user.is_staff:
        # If the user is_staff he will get the full set
        return get_QUERY_SETS()[query_set]
    else:
        # Otherwise we filter for all users that are in the responsible user group for that management user
        qs = get_QUERY_SETS()[query_set]
        filtered_users_qs = qs.filter(id__in=request.user.state.managed_users.all(), is_active=True)
        return filtered_users_qs

class AdvancedMatchingScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = TwoUserMatchingScore
        fields = '__all__'
        
    def to_representation(self, instance):
        representation =  super().to_representation(instance)

        assert 'user' in self.context
        user = self.context['user']
        partner = instance.user2 if user == instance.user1 else instance.user1
        
        markdown_info = ""
        for score in instance.scoring_results:
            markdown_info += f"## Function `{score['score_function']}`\n"
            try:
                markdown_info += f"{score['res']['markdown_info']}\n\n"
            except:
                markdown_info += "No markdown info available\n\n"
        
        representation['markdown_info'] = markdown_info

        representation['from_usr'] = {
            "uuid" : user.hash,
            "id" : user.id,
            **AdminUserSerializer(user).data
        }
        representation['to_usr'] = {
            "uuid" : partner.hash,
            "id" : partner.id,
            **AdminUserSerializer(partner).data
        }
        return representation

def matching_suggestion_from_database_paginated(request, user):
    matching_scores = TwoUserMatchingScore.get_matching_scores(user).order_by('-score')
    paginator = AugmentedPagination()
    pages = paginator.get_paginated_response(paginator.paginate_queryset(matching_scores, request)).data
    pages["results"] = AdvancedMatchingScoreSerializer(pages["results"], many=True, context={
        "user": user
    }).data
    return pages

def matching_scores_between_users(from_usr, to_usr):
    matching_score = TwoUserMatchingScore.get_score(from_usr, to_usr)
    if matching_score is None:
        total_score, matchable, results, score = score_between_db_update(from_usr, to_usr)
        matching_score = score

    return AdvancedMatchingScoreSerializer(matching_score, context={"user": from_usr}).data



class AdvancedAdminUserViewset(AdminViewSetExtensionMixin, viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdvancedAdminUserSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    @action(detail=True, methods=['get'])
    def scores(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        # TODO: use the IfHasControlOverUser permission here
        # TODO: if 'matching' user check if he has access to this user!
        
        # TODO: depricated new matching scores!!!
        scores = matching_suggestion_from_database_paginated(request, obj)
        return Response(scores)

    @action(detail=True, methods=['get'])
    def prematching_appointment(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
        return Response(PreMatchingAppointmentSerializer(PreMatchingAppointment.objects.filter(user=obj).first(), many=False).data)
    
    @action(detail=True, methods=['post'])
    def score_between(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        # TODO: depricated
        score = matching_scores_between_users(obj, request.data["to_user"])
        return Response(score)
    
    
    @action(detail=True, methods=['get'])
    def messages_mark_read(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()

        message_id = request.data['message_id']
        
        # First we check if the user is_staff or has matching permission and is responsible for that user
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        # Now we can check if 'obj'-user is in request.user.state.managed_users ( only if not staff )
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=obj.pk).exists():
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
            
        # Now we can check if the user has unread messages from that user
        message = Message.objects.get(
            uuid=message_id
        )
        print("Filtered messages", message)

        message.read = True
        message.save()

        return Response({
            "msg": "Message marked as read"
        })
        
        
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()

        return Response(AdvancedAdminUserSerializer(
            obj,
            context={'request': request, 'messages': True}
        ).data['messages'])
        
    @action(detail=True, methods=['get'])
    def sms(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        # First we check if the user is_staff or has matching permission and is responsible for that user
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
        
        # Now we can check if 'obj'-user is in request.user.state.managed_users ( only if not staff )
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=obj.pk).exists():
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            

        sms = SmsModel.objects.filter(recipient=obj).order_by('-created_at')
        
        return Response(SmsSerializer(sms, many=True).data)
        

    @action(detail=True, methods=['get'])
    def messages_reply(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        # First we check if the user is_staff or has matching permission and is responsible for that user
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        # Now we can check if 'obj'-user is in request.user.state.managed_users ( only if not staff )
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=obj.pk).exists():
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        message = obj.message(request.data['message'], sender=request.user)
        
        serialized = MessageSerializer(message).data

        return Response(serialized)
    
    
    @action(detail=True, methods=['get', 'post'])
    def resend_email(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        email_id = request.data['email_id']
        
        # First we check if the user is_staff or has matching permission and is responsible for that user
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        # Now we can check if 'obj'-user is in request.user.state.managed_users ( only if not staff )
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=obj.pk).exists():
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        from emails.models import EmailLog
        from emails.mails import get_mail_data_by_name
        
        email_log = EmailLog.objects.filter(receiver=obj, pk=email_id).first()
        subject = email_log.data["subject"] if "subject" in email_log.data else None
        
        if (subject is None):
            if (not ("subject" in request.data)):
                return Response({
                    "msg": "Cannot determine subject, please set one via 'subject' param"
                }, status=404)
            else:
                subject = request.data["subject"]

        params = email_log.data["params"]
        mail_data = get_mail_data_by_name(email_log.template)
        mail_params = mail_data.params(**params)
        
        obj.send_email(
            subject=subject,
            mail_data=mail_data,
            mail_params=mail_params,
        )
        
        return Response("Tried resending email")
    
    @action(detail=True, methods=['get', 'post'])
    def tasks(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        if request.method == 'POST':
            task = MangementTask.create_task(obj, request.data['description'], request.user)
            return Response(ManagementTaskSerializer(task).data)
        
        tasks = MangementTask.objects.filter(
            user=obj,
            state=MangementTask.MangementTaskStates.OPEN
        )

        return Response(ManagementTaskSerializer(tasks, many=True).data)

    @action(detail=True, methods=['post'])
    def complete_task(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        task = MangementTask.objects.get(pk=request.data['task_id'])
        task.state = MangementTask.MangementTaskStates.FINISHED
        task.save()
        return Response(ManagementTaskSerializer(task).data)
    
    @action(detail=True, methods=['get', 'post'])
    def notes(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        _os = obj.state
        
        if request.method == 'POST':
            _os.notes = request.data['notes']
            _os.save()
            return Response(_os.notes)
        else:
            if not _os.notes:
                _os.notes = ""
                _os.save()
            return Response(_os.notes)

    
    @action(detail=True, methods=['get'])
    def request_score_update(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        consider_within_days = int(request.query_params.get('days_searching', 60))
        
        from management.tasks import matching_algo_v2
        from management.api.scores import calculate_scores_user
        task = matching_algo_v2.delay(
            pk,
            consider_within_days
        )
        return Response({
            "task_id": task.id
        })
        
class SimpleUserViewSet(AdvancedAdminUserViewset):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdminUserSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            # assume uuid
            return super().get_object()
        else:
            return super().get_queryset().get(hash=self.kwargs["pk"])


def check_task_status(task_id):
    from celery.result import AsyncResult
    task = AsyncResult(task_id)
    
    return {
        "state": task.state,
        "info": json.loads(json.dumps(task.info, cls=DjangoJSONEncoder, default=lambda o: str(o))),
    }
    
    
    
@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def request_task_status(request, task_id):
    # TODO: there should be an additional restrictioon here for 'matching' users.
    # Currently any user with 'matching' permission can request task status for any user
    # But they generaly never contain sensitive information
    return Response(check_task_status(task_id))

@extend_schema(
    responses=inline_serializer(
        name="UserListQuerySetEnum",
        fields={
            "count": serializers.IntegerField(),
            "page": serializers.IntegerField(),
            "next": serializers.URLField(),
            "previous": serializers.URLField(),
            "results": AdvancedAdminUserSerializer(many=True)
        }
    )
)
@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def get_user_list_users(request, query_set):

    page = request.query_params.get('page', 1)
    items_per_page = request.query_params.get('items_per_page', 40)

    user_viewset = make_user_viewset(get_staff_queryset(query_set, request), items_per_page=items_per_page)
    user_lists = user_viewset.emulate(request).list()

    return Response(user_lists)

root_user_viewset = AdvancedAdminUserViewset
user_info_viewset = SimpleUserViewSet

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def user_info_by_id_or_hash(request, id: str):
    
    # check if Id is a parsable int, otherwise assume a hash
    if not id.isnumeric():
        return Response(AdvancedAdminUserSerializer(
            User.objects.get(hash=id),
            context={'request': request}
        ).data)
    else:
        return Response(AdvancedAdminUserSerializer(
            User.objects.get(pk=int(id)),
            context={'request': request}
        ).data)

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def advanced_user_listing(request, list):

    page = request.query_params.get('page', 1)
    items_per_page = request.query_params.get('items_per_page', 40)

    user_viewset = make_user_viewset(get_staff_queryset(list, request), items_per_page=items_per_page)

    user_lists = {}
    user_lists[list] = user_viewset.emulate(request).list()

    return Response({
        "query_sets": QuerySetEnum.as_dict(),
        "user_lists": user_lists
    })
    

def default_admin_data(user):
    return {
        "is_admin": user.is_staff,
    } 
    

@extend_schema(
    responses=inline_serializer(
        name="UserListQuerySetOptionsEnum",
        fields={
            "lists": serializers.DictField()
        }
    )
)
@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def get_user_list_query_sets(request):
    return Response({"lists": QuerySetEnum.as_dict()})

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def admin_panel_v2(request, menu="root"):
    print("MENU", menu)
    
    if menu.startswith("users"):

        return render(request, "admin_pannel_v2_frontend.html", { "data" : json.dumps({
            "query_sets": QuerySetEnum.as_dict(),
            "user_lists": {},
        },cls=DjangoJSONEncoder, default=lambda o: str(o))})
    else:
        return render(request, "admin_pannel_v2_frontend.html", { "data" : json.dumps(default_admin_data(request.user), cls=DjangoJSONEncoder, default=lambda o: str(o))})
    

@api_view(['GET', 'POST'])
@permission_classes([])
def admin_panel_v2_login(request):
    if request.method == 'POST': 
        from django.contrib.auth import authenticate, login
        user = authenticate(request, username=request.data['email'], password=request.data['password'])
        if (user is not None) and user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            login(request, user)
            return Response({
                "msg": "Successfully logged in",
                "user": AdminUserSerializer(user).data
            })
        else:
            return Response({
                "msg": "Invalid credentials or not a Matching User!"
            }, status=401)
    else:
        return render(request, "admin_pannel_v2_login.html", { 
            "data" : json.dumps({}, cls=DjangoJSONEncoder, default=lambda o: str(o))
        })
