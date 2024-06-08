from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets
from django.urls import path
from django_filters import rest_framework as filters
from management.models.scores import TwoUserMatchingScore
from management.models.user import User
from management.models.profile import Profile, MinimalProfileSerializer
from management.models.pre_matching_appointment import PreMatchingAppointment, PreMatchingAppointmentSerializer
from management.views.admin_panel_v2 import IsAdminOrMatchingUser
from typing import OrderedDict
from rest_framework import serializers
from drf_spectacular.openapi import AutoSchema
from drf_spectacular.utils import extend_schema_view, extend_schema
from dataclasses import dataclass
from drf_spectacular.utils import extend_schema, inline_serializer
from management.api.user_advanced_filter_lists import FILTER_LISTS, FilterListEntry
from management.api.user_data import get_paginated, serialize_proposed_matches, AdvancedUserMatchSerializer
from management.models.matches import Match
from management.models.unconfirmed_matches import ProposedMatch
from management.models.state import State, StateSerializer
from management.models.sms import SmsModel, SmsSerializer
from management.models.management_tasks import MangementTask, ManagementTaskSerializer
from chat.models import Message, MessageSerializer
from management.api.scores import score_between_db_update
from management.tasks import matching_algo_v2
from django.core.paginator import Paginator
from rest_framework.pagination import PageNumberPagination
from rest_framework.utils import serializer_helpers
from django.utils import timezone
from datetime import timedelta, datetime
import json
from drf_spectacular.generators import SchemaGenerator
from enum import Enum
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from drf_spectacular.generators import SchemaGenerator

class AdvancedUserSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = User
        fields = ['hash', 'id', 'email', 'date_joined', 'last_login']
        
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['profile'] = MinimalProfileSerializer(instance.profile).data
        
        items_per_page = 5
        user = instance
        confirmed_matches = get_paginated(Match.get_confirmed_matches(user), items_per_page, 1)
        confirmed_matches["items"] = AdvancedUserMatchSerializer(
            confirmed_matches["items"], 
            many=True, 
            context={
                'user': user,
                'status': 'confirmed'
        }).data

        unconfirmed_matches = get_paginated(Match.get_unconfirmed_matches(user), items_per_page, 1)
        unconfirmed_matches["items"] = AdvancedUserMatchSerializer(
            unconfirmed_matches["items"], 
            many=True, 
            context={
                'user': user,
                'status': 'unconfirmed'
        }).data

        support_matches = get_paginated(Match.get_support_matches(user), items_per_page, 1)
        support_matches["items"] = AdvancedUserMatchSerializer(
            support_matches["items"], 
            many=True, 
            context={
                'user': user,
                'status': 'support'
        }).data

        proposed_matches = get_paginated(ProposedMatch.get_open_proposals_learner(user), items_per_page, 1)
        proposed_matches["items"] = serialize_proposed_matches(proposed_matches["items"], user)
        
        representation['matches'] = {
            "confirmed": confirmed_matches,
            "unconfirmed": unconfirmed_matches,
            "support": support_matches,
            "proposed": proposed_matches
        }
        
        representation['state'] = StateSerializer(instance.state).data

        return representation

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
            **AdvancedUserSerializer(user).data
        }
        representation['to_usr'] = {
            "uuid" : partner.hash,
            "id" : partner.id,
            **AdvancedUserSerializer(partner).data
        }
        return representation
    
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

class UserFilter(filters.FilterSet):
    
    profile__user_type = filters.ChoiceFilter(
        field_name='profile__user_type', 
        choices=Profile.TypeChoices.choices, 
        help_text='Filter for learner or volunteers'
    )

    state__email_authenticated = filters.BooleanFilter(
        field_name='state__email_authenticated',
        help_text='Filter for users that have authenticated their email'
    )

    state__had_prematching_call = filters.BooleanFilter(
        field_name='state__had_prematching_call',
        help_text='Filter for users that had a prematching call'
    )

    joined_between = filters.DateFromToRangeFilter(
        field_name='date_joined',
        help_text='Range filter for when the user joined the platform, accepts string datetimes'
    )

    loggedin_between = filters.DateFromToRangeFilter(
        field_name='last_login',
        help_text='Range filter for when the user last logged in, accepts string datetimes'
    )

    state__company = filters.ChoiceFilter(
        field_name='state__company', 
        choices=[("null", None), ("accenture", "accenture")],
        help_text='Filter for users that are part of a company'
    )
    
    list = filters.ChoiceFilter(
        field_name='list',
        choices=[(entry.name, entry.description) for entry in FILTER_LISTS],
        method='filter_list',
        help_text='Filter for users that are part of a list'
    )
    
    def filter_list(self, queryset, name, value):
        selected_filter = next(filter(lambda entry: entry.name == value, FILTER_LISTS))
        if selected_filter.queryset:
            return selected_filter.queryset(queryset)
        else:
            return queryset

    class Meta:
        model = User
        fields = ['hash', 'id', 'email']
        

class DynamicFilterSerializer(serializers.Serializer):
    filter_type = serializers.CharField()
    name = serializers.CharField()
    nullable = serializers.BooleanField(default=False)
    value_type = serializers.CharField(required=False)
    description = serializers.CharField(required=False)
    choices = serializers.ListField(child=serializers.DictField(), required=False)
    lookup_expr = serializers.ListField(child=serializers.CharField(), required=False)

def matching_suggestion_from_database_paginated(request, user):
    return pages

@extend_schema_view(
    list=extend_schema(summary='List users'),
    retrieve=extend_schema(summary='Retrieve user'),
)
class AdvancedUserViewset(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')

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
        
    @action(detail=False, methods=['get'])
    def get_filter_schema(self, request, include_lookup_expr=False):
        # 1 - retrieve all the filters
        filterset = self.filterset_class()
        _filters = []
        for field_name, filter_instance in filterset.get_filters().items():
            filter_data = {
                'name': field_name,
                'filter_type': type(filter_instance).__name__,
            }
            
            choices = getattr(filter_instance, 'extra', {}).get('choices', [])
            if len(choices):
                filter_data['choices'] = [{
                    "tag": choice[1],
                    "value": choice[0]
                } for choice in choices]

            if 'help_text' in filter_instance.extra:
                filter_data['description'] = filter_instance.extra['help_text']
            
            if include_lookup_expr:
                if isinstance(filter_instance, filters.RangeFilter):
                    filter_data['lookup_expr'] = ['exact', 'gt', 'gte', 'lt', 'lte', 'range']
                elif isinstance(filter_instance, filters.BooleanFilter):
                    filter_data['lookup_expr'] = ['exact']
                else:
                    filter_data['lookup_expr'] = [filter_instance.lookup_expr] if isinstance(filter_instance.lookup_expr, str) else filter_instance.lookup_expr
            serializer = DynamicFilterSerializer(data=filter_data)

            serializer.is_valid(raise_exception=True)
            _filters.append(serializer.data)
        # 2 - retrieve the query shema
        generator = SchemaGenerator(
            patterns=None,
            urlconf=None
        )
        schema = generator.get_schema(request=request)
        view_key = f'/api/matching/users/'  # derive the view key based on your routing
        filter_schemas = schema['paths'].get(view_key, {}).get('get', {}).get('parameters', [])
        for filter_schema in filter_schemas:
            for filter_data in _filters:
                if filter_data['name'] == filter_schema['name']:
                    filter_data['value_type'] = filter_schema['schema']['type']
                    filter_data['nullable'] = filter_schema['schema'].get('nullable', False)
                    break
        return Response({
            "filters": _filters,
            "lists": [entry.to_dict() for entry in FILTER_LISTS]
        })

    def get_object(self):
        if isinstance(self.kwargs["pk"], int):
            return super().get_object()
        elif self.kwargs["pk"].isnumeric():
            self.kwargs["pk"] = int(self.kwargs["pk"])
            return super().get_object()
        else:
            return super().get_queryset().get(hash=self.kwargs["pk"])

    @action(detail=True, methods=['get'])
    def scores(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        matching_scores = TwoUserMatchingScore.get_matching_scores(user).order_by('-score')
        paginator = AugmentedPagination()
        pages = paginator.get_paginated_response(paginator.paginate_queryset(matching_scores, request)).data
        pages["results"] = AdvancedMatchingScoreSerializer(pages["results"], many=True, context={
            "user": obj
        }).data
        return Response(pages)

    @action(detail=True, methods=['get'])
    def prematching_appointment(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        latest_appointment = PreMatchingAppointment.objects.filter(user=obj).order_by('-created').first()
        return Response(PreMatchingAppointmentSerializer(latest_appointment, many=False).data)
    
    @extend_schema(
        request=inline_serializer(
            name='ScoreBetweenRequest',
            fields={
                'to_user': serializers.CharField()
            }
        )
    )
    @action(detail=True, methods=['post'])
    def score_between(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        from_usr = obj
        to_usr = request.data['to_user']
        matching_score = TwoUserMatchingScore.get_score(from_usr, to_usr)
        if matching_score is None:
            total_score, matchable, results, score = score_between_db_update(from_usr, to_usr)
            matching_score = score

        score = AdvancedMatchingScoreSerializer(matching_score, context={"user": from_usr}).data
        return Response(score)
    
    @action(detail=True, methods=['get'])
    def messages_mark_read(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()

        message_id = request.data['message_id']
        
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=obj.pk).exists():
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        message = Message.objects.get(uuid=message_id)
        message.read = True
        message.save()

        return Response({
            "msg": "Message marked as read"
        })
        
    @action(detail=True, methods=['get'])
    def delete_message(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()

        message_id = request.data['message_id']
        
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=obj.pk).exists():
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
        message = Message.objects.get(uuid=message_id)
        message.delete()

        return Response({
            "msg": "Message deleted"
        })
        
    @action(detail=True, methods=['get'])
    def messages(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()

        return Response(AdvancedUserSerializer(
            obj,
            context={'request': request, 'messages': True}
        ).data['messages'])
        
    @action(detail=True, methods=['get'])
    def sms(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
        
        if not request.user.is_staff and not request.user.state.managed_users.filter(pk=obj.pk).exists():
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)

        sms = SmsModel.objects.filter(recipient=obj).order_by('-created_at')
        
        return Response(SmsSerializer(sms, many=True).data)

    @action(detail=True, methods=['post'])
    def messages_reply(self, request, pk=None):
        self.kwargs['pk'] = pk
        obj = self.get_object()
        
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
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
        
        if not request.user.is_staff and not request.user.state.has_extra_user_permission(State.ExtraUserPermissionChoices.MATCHING_USER):
            return Response({
                "msg": "You are not allowed to access this user!"
            }, status=401)
            
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
        
        task = matching_algo_v2.delay(
            pk,
            consider_within_days
        )
        return Response({
            "task_id": task.id
        })
        
viewset_actions = [
     path('api/matching/users/<pk>/scores/', AdvancedUserViewset.as_view({'get': 'scores'})),
    path('api/matching/users/<pk>/prematching_appointment/', AdvancedUserViewset.as_view({'get': 'prematching_appointment'})),
    path('api/matching/users/<pk>/score_between/', AdvancedUserViewset.as_view({'post': 'score_between'})),
    path('api/matching/users/<pk>/messages_mark_read/', AdvancedUserViewset.as_view({'get': 'messages_mark_read'})),
    path('api/matching/users/<pk>/messages/', AdvancedUserViewset.as_view({'get': 'messages'})),
    path('api/matching/users/<pk>/sms/', AdvancedUserViewset.as_view({'get': 'sms'})),
    path('api/matching/users/<pk>/messages_reply/', AdvancedUserViewset.as_view({'post': 'messages_reply'})),
    path('api/matching/users/<pk>/resend_email/', AdvancedUserViewset.as_view({'get': 'resend_email', 'post': 'resend_email'})),
    path('api/matching/users/<pk>/tasks/', AdvancedUserViewset.as_view({'get': 'tasks', 'post': 'tasks'})),
    path('api/matching/users/<pk>/complete_task/', AdvancedUserViewset.as_view({'post': 'complete_task'})),
    path('api/matching/users/<pk>/notes/', AdvancedUserViewset.as_view({'get': 'notes', 'post': 'notes'})),
    path('api/matching/users/<pk>/request_score_update/', AdvancedUserViewset.as_view({'get': 'request_score_update'})),
    path('api/matching/users/<pk>/delete_message/', AdvancedUserViewset.as_view({'get': 'delete_message'})),
]

api_urls = [
    path('api/matching/users/', AdvancedUserViewset.as_view({'get': 'list'})),
    path('api/matching/users/filters/', AdvancedUserViewset.as_view({'get': 'get_filter_schema'})),
    path('api/matching/users/<pk>/', AdvancedUserViewset.as_view({'get': 'retrieve'})),
    *viewset_actions
]