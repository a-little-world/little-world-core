from django.contrib.auth.decorators import user_passes_test
from rest_framework import viewsets, serializers
from rest_framework.permissions import IsAdminUser
from django.core.paginator import Paginator
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
)
from emails.models import EmailLog, EmailLogSerializer, AdvancedEmailLogSerializer
from typing import OrderedDict
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.utils import serializer_helpers


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
            print("TBS", match, match['partner']['id'])
            partner = controller.get_user_by_pk(match['partner']['id'])
            if not DialogsModel.dialog_exists(partner, instance):
                return None
            return get_paginated(MessageModel.get_messages_for_dialog(partner, instance), 10, 1)
        
        confirmed = representation['matches']['confirmed']['items']
        support = representation['matches']['support']['items']
        
        # No dialogs exists with unconfirmed matches!
        # unconfirmed = representation['matches']['unconfirmed']['items']
        messages = {}
        for match in [*confirmed, *support]:
            # It can happen that a dialog was aready deleted it this was a past match
            # TODO: this somethimes causes an error in prod, just not loading the messages for that chat should be ok.
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
    unfinished_registration = "Users who have not finished the user form, but verfied their email!"
    
    def as_dict():
        return {i.name: i.value for i in QuerySetEnum}
    
QUERY_SETS = {
    QuerySetEnum.all.name: User.objects.all().order_by('-date_joined'),
    QuerySetEnum.searching.name: User.objects.filter(
        state__matching_state=State.MatchingStateChoices.SEARCHING
    ).order_by('-date_joined'),
}

def get_staff_queryset(query_set, request):
    # TODO: this should in the future be used to restrict the access of specific user groups to specific staff users
    # Should be done by checking a condition and then filtering the queryset additionally...
    return QUERY_SETS[query_set]

root_user_viewset = make_user_viewset(QUERY_SETS[QuerySetEnum.all.name], _serializer_class=AdvancedAdminUserSerializer).as_view({
    'get': 'retrieve',
})

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_panel_v2(request, query_set=QuerySetEnum.all.name):

    if query_set not in QUERY_SETS:
        return Response(status=404)
    
    page = request.query_params.get('page', 1)
    items_per_page = request.query_params.get('items_per_page', 40)
    
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