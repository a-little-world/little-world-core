from django.contrib.auth.decorators import user_passes_test
from rest_framework import viewsets, serializers
from rest_framework.permissions import IsAdminUser
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
    ProposalProfileSerializer
)
from emails.models import EmailLog, EmailLogSerializer, AdvancedEmailLogSerializer
from typing import OrderedDict
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.utils import serializer_helpers
from django.db.models import Q

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
                "id": str(partner.hash),
                **ProfileSerializer(partner.profile).data
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
        permission_classes = [IsAdminUser]
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

    confirmed_matches = get_paginated(models.Match.get_confirmed_matches(user), items_per_page, 1)
    confirmed_matches["items"] = serialize_matches(confirmed_matches["items"], user)

    unconfirmed_matches = get_paginated(models.Match.get_unconfirmed_matches(user), items_per_page, 1)
    unconfirmed_matches["items"] = serialize_matches(unconfirmed_matches["items"], user)

    support_matches = get_paginated(models.Match.get_support_matches(user), items_per_page, 1)
    support_matches["items"] = serialize_matches(support_matches["items"], user)
    
    proposed_matches = get_paginated(models.UnconfirmedMatch.get_open_proposals(user), items_per_page, 1)
    proposed_matches["items"] = serialize_proposed_matches(proposed_matches["items"], user)
    
    representation['matches'] = {
        "confirmed": confirmed_matches,
        "unconfirmed": unconfirmed_matches,
        "support": support_matches
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
        representation = super().to_representation(instance)
        representation = update_representation(representation, instance)
        
        # Now also add the matches messages
        # And the chat with that user
        
        def get_messages(match):
            partner = controller.get_user_by_pk(match['partner']['id'])
            print("TBS", partner, instance)
            try:
                _msgs = MessageModel.objects.filter(
                    Q(sender=partner, recipient=instance) | Q(sender=instance, recipient=partner)
                )
                messages = get_paginated(_msgs, 10, 1)
                print("MSGS", messages, _msgs)
            except Exception as e:
                print("ERR retrieving messages" , repr(e))
                # TODO: handle better
                return None
            if not DialogsModel.get_dialog_for_user_as_object(partner, instance).exists():
                messages["no_dialog"] = True # prop means it has been deleted
            return messages
        
        confirmed = representation['matches']['confirmed']['items']
        support = representation['matches']['support']['items']
        unconfirmed = representation['matches']['unconfirmed']['items']
        
        messages = {}
        for match in [*confirmed, *support, *unconfirmed]:
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
    
    def as_dict():
        return {i.name: i.value for i in QuerySetEnum}
    
def three_weeks_ago():
    from datetime import datetime, timedelta
    return datetime.now() - timedelta(weeks=3)

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

    
QUERY_SETS = {
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
    QuerySetEnum.highquality_matching.name: get_quality_match_querry_set()
    
}

def get_staff_queryset(query_set, request):
    # TODO: this should in the future be used to restrict the access of specific user groups to specific staff users
    # Should be done by checking a condition and then filtering the queryset additionally...
    return QUERY_SETS[query_set]

def matching_suggestion_from_database_paginated(request, user):
    from ..models.matching_scores import MatchinScore, MatchingScoreSerializer
    matching_scores = MatchinScore.objects.filter(from_usr=user, current_score=True)
    paginator = AugmentedPagination()
    pages = paginator.get_paginated_response(paginator.paginate_queryset(matching_scores, request)).data
    pages["results"] = MatchingScoreSerializer(pages["results"], many=True).data
    return pages


class AdvancedAdminUserViewset(AdminViewSetExtensionMixin, viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdvancedAdminUserSerializer
    pagination_class = DetailedPaginationMixin
    
    @action(detail=True, methods=['get'])
    def scores(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        scores = matching_suggestion_from_database_paginated(request, obj)
        return Response(scores)

root_user_viewset = AdvancedAdminUserViewset

@api_view(['GET'])
@permission_classes([IsAdminUser])
def advanced_user_listing(request, list):

    page = request.query_params.get('page', 1)
    items_per_page = request.query_params.get('items_per_page', 40)

    user_viewset = make_user_viewset(get_staff_queryset(list, request), items_per_page=items_per_page)

    user_lists = {}
    user_lists[list] = user_viewset.emulate(request).list()

    return Response({
        "query_sets": QuerySetEnum.as_dict(),
        "user_lists": user_lists,
    })

@api_view(['GET'])
@permission_classes([IsAdminUser])
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