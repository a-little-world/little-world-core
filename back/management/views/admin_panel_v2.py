from django.contrib.auth.decorators import user_passes_test
from rest_framework import viewsets, serializers
from rest_framework.permissions import IsAdminUser
from django.core.paginator import Paginator
from django.shortcuts import render
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from management import models
from enum import Enum
import json
from ..models import (
    User,
    State,
    ProfileSerializer,
    StateSerializer
)
from typing import OrderedDict
from django.core.serializers.json import DjangoJSONEncoder


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
    page_size = 40
    max_page_size = 40
    
    def get_paginated_response(self, data):
        return Response(OrderedDict([
            ('count', self.page.paginator.count),
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

class AdminUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ['hash', 'email', 'date_joined', 'last_login']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        
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


class AdminUserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = AdminUserSerializer 
    
def make_user_viewset(_queryset, _serializer_class=AdminUserSerializer):
    class __EmulatedUserViewset(AdminViewSetExtensionMixin, viewsets.ModelViewSet):
        queryset = _queryset
        serializer_class = _serializer_class
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

@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_panel_v2(request, query_set=QuerySetEnum.all.name):

    if query_set not in QUERY_SETS:
        return Response(status=404)
    
    page = request.query_params.get('page', 1)
    items_per_page = request.query_params.get('items_per_page', 40)
    
    user_viewset = make_user_viewset(get_staff_queryset(query_set, request))
    
    user_lists = {}
    user_lists[query_set] = user_viewset.emulate(request).list()
    
    if not ("all" in user_lists):
        all_viewset = make_user_viewset(get_staff_queryset("all", request))
        user_lists["all"] = all_viewset.emulate(request).list()

    return render(request, "admin_pannel_v2_frontend.html", { "data" : json.dumps({
        "query_sets": QuerySetEnum.as_dict(),
        "user_lists": user_lists,
    },cls=DjangoJSONEncoder, default=lambda o: str(o))})