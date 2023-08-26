from django.contrib.auth.decorators import user_passes_test
from rest_framework import viewsets, serializers
from rest_framework.permissions import IsAdminUser, BasePermission
from django.core.paginator import Paginator
from rest_framework.decorators import action
from django.shortcuts import render
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from chat.django_private_chat2.models import MessageModel, DialogsModel
from chat.django_private_chat2.serializers import serialize_message_model
from management import models
from management import controller
from enum import Enum
import json
from ..models import (
    User,
    State,
    ProfileSerializer,
    StateSerializer,
    ProposalProfileSerializer,
    MatchinScore
)
from emails.models import EmailLog, EmailLogSerializer, AdvancedEmailLogSerializer
from typing import OrderedDict
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.utils import serializer_helpers
from django.db.models import Q

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

    print("updating representations for ", user, instance)
    confirmed_matches = get_paginated(models.Match.get_confirmed_matches(user), items_per_page, 1)
    confirmed_matches["items"] = serialize_matches(confirmed_matches["items"], user)
    
    print("confirmed matches", [f'{i["partner"]["id"]} m_id {i["id"]}' for i in confirmed_matches["items"]])

    unconfirmed_matches = get_paginated(models.Match.get_unconfirmed_matches(user), items_per_page, 1)
    unconfirmed_matches["items"] = serialize_matches(unconfirmed_matches["items"], user)

    print("unconfirmed matches", [f'{i["partner"]["id"]} m_id {i["id"]}' for i in unconfirmed_matches["items"]])

    support_matches = get_paginated(models.Match.get_support_matches(user), items_per_page, 1)
    support_matches["items"] = serialize_matches(support_matches["items"], user)
    
    proposed_matches = get_paginated(models.UnconfirmedMatch.get_open_proposals(user), items_per_page, 1)
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
    
class AdvancedAdminUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['hash', 'id', 'email', 'date_joined', 'last_login']
    
    def to_representation(self, instance):
        print("SERIALIZING", instance)
        representation = super().to_representation(instance)
        representation = update_representation(representation, instance)
        
        # Now also add the matches messages
        # And the chat with that user
        
        def get_messages(match):
            partner = controller.get_user_by_pk(match['partner']['id'])
            print("TBS", partner, instance)
            _msgs = MessageModel.objects.filter(
                Q(sender=partner, recipient=instance) | Q(sender=instance, recipient=partner)
            )
            messages = get_paginated(_msgs, 10, 1)
            if not DialogsModel.get_dialog_for_user_as_object(partner, instance).exists():
                messages["no_dialog"] = True # prop means it has been deleted
            return messages
        
        confirmed = representation['matches']['confirmed']['items']
        support = representation['matches']['support']['items']
        unconfirmed = representation['matches']['unconfirmed']['items']
        
        messages = {}
        for match in [*confirmed, *support, *unconfirmed]:
            print("TBS", match["partner"]["id"], match["partner"]["first_name"])
            partner = controller.get_user_by_pk(match['partner']['id'])
            print("PARTNER", partner)
            _msg = get_messages(match)
            if _msg is None:
                continue
            messages[match['id']] = _msg
            messages[match['id']]["match"] = {
                "match_id": match['id'],
                "profile": match['partner']
            }
            messages[match['id']]["items"] = [serialize_message_model(item, instance.pk) for item in _msg["items"]]
            
        representation['messages'] = messages

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
    in_registration = "Users who have not finished the user form or verified their email!"
    active_within_3weeks = "Users who have been active within the last 3 weeks!"
    highquality_matching = "Users who have at least one matching with 20+ Messages"
    message_reply_required = "Users who have a unread message to the admin user"
    
    def as_dict():
        return {i.name: i.value for i in QuerySetEnum}
    
def three_weeks_ago():
    from datetime import datetime, timedelta
    return datetime.now() - timedelta(weeks=3)

def get_user_with_message_to_admin():
    # TODO: in the future each staff mover has to be filtered here individually
    
    from django.db.models import Subquery, OuterRef, Count
    admin_pk = controller.get_base_management_user().pk
    unread_messages = MessageModel.objects.filter(
        recipient_id=admin_pk,
        read=False
    )
    unread_senders_ids = unread_messages.values("sender")
    sender_users = User.objects.filter(id__in=Subquery(unread_senders_ids))
    return sender_users
    

def get_quality_match_querry_set():
    
    from django.db.models import Subquery, OuterRef, Count
    from management.models import Match

    # Create a subquery object to annotate the match with msg_count
    sq = MessageModel.objects.filter(
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

    
def get_QUERY_SETS():
    return {
        QuerySetEnum.all.name: User.objects.all().order_by('-date_joined'),
        QuerySetEnum.searching.name: User.objects.filter(
            state__user_form_state=State.UserFormStateChoices.FILLED,
            state__email_authenticated=True,
            state__matching_state=State.MatchingStateChoices.SEARCHING
        ).order_by('-date_joined'),
        QuerySetEnum.in_registration.name: User.objects.filter(
            Q(state__user_form_state=State.UserFormStateChoices.UNFILLED) | Q(state__email_authenticated=False)).order_by('-date_joined'),
        QuerySetEnum.active_within_3weeks.name: User.objects.filter(
            last_login__gte=three_weeks_ago()).order_by('-date_joined'),
        QuerySetEnum.highquality_matching.name: get_quality_match_querry_set(),
        QuerySetEnum.message_reply_required.name: get_user_with_message_to_admin(),
        
    }

def get_staff_queryset(query_set, request):
    # Should be done by checking a condition and then filtering the queryset additionally...
    if request.user.is_staff:
        # If the user is_staff he will get the full set
        return get_QUERY_SETS()[query_set]
    else:
        # Otherwise we filter for all users that are in the responsible user group for that management user
        qs = get_QUERY_SETS()[query_set]
        filtered_users_qs = qs.filter(id__in=request.user.state.managed_users.all())
        return filtered_users_qs

class AdvancedMatchingScoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = MatchinScore
        fields = '__all__'
        
    def to_representation(self, instance):
        representation =  super().to_representation(instance)
        
        representation['from_usr'] = {
            "uuid" : instance.from_usr.hash,
            "id" : instance.from_usr.id,
            **AdminUserSerializer(instance.from_usr).data
        }
        representation['to_usr'] = {
            "uuid" : instance.to_usr.hash,
            "id" : instance.to_usr.id,
            **AdminUserSerializer(instance.to_usr).data
        }
        return representation

def matching_suggestion_from_database_paginated(request, user):
    from ..models.matching_scores import MatchinScore, MatchingScoreSerializer
    matching_scores = MatchinScore.objects.filter(from_usr=user, current_score=True, matchable=True).order_by('-score')
    paginator = AugmentedPagination()
    pages = paginator.get_paginated_response(paginator.paginate_queryset(matching_scores, request)).data
    pages["results"] = AdvancedMatchingScoreSerializer(pages["results"], many=True).data
    return pages


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
        
        scores = matching_suggestion_from_database_paginated(request, obj)
        return Response(scores)
    
    @action(detail=True, methods=['get', 'post'])
    def notes(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        if request.method == 'POST':
            obj.state.notes = request.data['notes']
            obj.state.save()
            return Response(obj.state.notes)
        else:
            return Response(obj.state.notes)

    
    @action(detail=True, methods=['get'])
    def request_score_update(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        from management.tasks import calculate_directional_matching_score_v2_static
        task = calculate_directional_matching_score_v2_static.delay(
            obj.pk,
            catch_exceptions=True,
            invalidate_other_scores=True
        )
        
        return Response({
            "msg": "Task dispatched scores will be written to db on task completion",
            "task_id": task.task_id,
            "view": f"/admin/django_celery_results/taskresult/?q={task.task_id}"
        })
        
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

root_user_viewset = AdvancedAdminUserViewset

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
    
    

@api_view(['GET'])
@permission_classes([IsAdminOrMatchingUser])
def admin_panel_v2(request):

    page = request.query_params.get('page', 1)
    items_per_page = request.query_params.get('items_per_page', 40)
    
    query_set = request.query_params.get('list', QuerySetEnum.all.name)
    
    user_viewset = make_user_viewset(get_staff_queryset(query_set, request), items_per_page=items_per_page)
    
    user_lists = {}
    user_lists[query_set] = user_viewset.emulate(request).list()
    
    if not ("all" in user_lists):
        all_viewset = make_user_viewset(get_staff_queryset("all", request), items_per_page=items_per_page)
        user_lists["all"] = all_viewset.emulate(request).list()
        

    return render(request, "admin_pannel_v2_frontend.html", { "data" : json.dumps({
        "query_sets": QuerySetEnum.as_dict(),
        "user_lists": user_lists,
    },cls=DjangoJSONEncoder, default=lambda o: str(o))})
    

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