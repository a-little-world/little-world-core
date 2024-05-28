from management.views.admin_panel_v2 import DetailedPaginationMixin, IsAdminOrMatchingUser
from management.models.user import User
from management.models.profile import Profile
from rest_framework import viewsets
from rest_framework import serializers
from django.urls import path
from django_filters import rest_framework as filters
from rest_framework.decorators import action
from rest_framework.response import Response
from back.utils import get_options_serializer

class AdvancedUserSerializer(serializers.ModelSerializer):
    
    def get_options(self, obj):
        return get_options_serializer(self, obj)

    class Meta:
        model = User
        fields = ['hash', 'id', 'email', 'date_joined', 'last_login']
        
class UserFilter(filters.FilterSet):
    
    profile__user_type = filters.ChoiceFilter(field_name='profile__user_type', choices=Profile.TypeChoices.choices)
    state__email_authenticated = filters.BooleanFilter(field_name='state__email_authenticated')
    state__had_prematching_call = filters.BooleanFilter(field_name='state__had_prematching_call')
    joined_between = filters.DateFromToRangeFilter(field_name='date_joined')
    loggedin_between = filters.DateFromToRangeFilter(field_name='last_login')
    state__company = filters.ChoiceFilter(field_name='state__company', choices=[("null", None), ("Accenture", "accenture")])

    class Meta:
        model = User
        fields = ['hash', 'id', 'email', 'date_joined', 'last_login']

class AdvancedUserViewset(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')

    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = UserFilter

    serializer_class = AdvancedUserSerializer
    pagination_class = DetailedPaginationMixin
    permission_classes = [IsAdminOrMatchingUser]
    
    @action(detail=False, methods=['get'])
    def get_options_all(self, request):
        from management.controller import get_base_management_user
        user = get_base_management_user()
        return Response(self.get_serializer(user).get_options(user))
    
    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            # assume uuid
            return super().get_object()
        else:
            return super().get_queryset().get(hash=self.kwargs["pk"])


api_urls = [
    path('api/matching/users/', AdvancedUserViewset.as_view({'get': 'list'})),
    path('api/matching/users/options/', AdvancedUserViewset.as_view({'get': 'get_options_all'})),
    path('api/matching/users/<pk>/', AdvancedUserViewset.as_view({'get': 'retrieve'})),
]