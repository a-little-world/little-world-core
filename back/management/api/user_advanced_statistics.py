from rest_framework.decorators import action, api_view, permission_classes
from video.models import LivekitSession
from django.db.models.functions import TruncDay, TruncWeek, ExtractDay, TruncMonth
from rest_framework.response import Response
from management.api.user_advanced_filter_lists import USER_JOURNEY_FILTER_LISTS
from management.api.match_journey_filter_list import MATCH_JOURNEY_FILTERS
from chat.models import Message, Chat
from rest_framework import viewsets
from datetime import timedelta, date
from django.db.models import Q, Count, F, Avg, Sum
from django.conf import settings
from management.controller import delete_user, make_tim_support_user
from management.twilio_handler import _get_client
from emails.models import EmailLog, AdvancedEmailLogSerializer
from emails.mails import get_mail_data_by_name
from django.urls import path
from django_filters import rest_framework as filters
from management.models.scores import TwoUserMatchingScore
from management.models.user import User
from management.views.matching_panel import DetailedPaginationMixin, AugmentedPagination, IsAdminOrMatchingUser
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

@extend_schema(
    request=inline_serializer(
        name='UserStatisticsCountOverTimeRequest',
        fields={
            'bucket_size': serializers.IntegerField(default=1),
            'base_list': serializers.ChoiceField(
                choices=[entry.name for entry in FILTER_LISTS],
                default='all',
            ),
            'start_date': serializers.DateField(default='2022-01-01'),
            'end_date': serializers.DateField(default=date.today())
        }
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def user_signups(request):
    # Validate the inputs
    today = date.today()
    bucket_size = request.data.get('bucket_size', 1)
    start_date = request.data.get('start_date', '2022-01-01')
    end_date = request.data.get('end_date', today)
    cumulative = request.query_params.get('cumulative', False)
    
    list_name = request.data.get('base_list', 'all')
    selected_filter = next(filter(lambda entry: entry.name == list_name, FILTER_LISTS))
    
    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())
    
    queryset = selected_filter.queryset(qs=pre_filtered_users)

    if bucket_size == 1:
        trunc_func = TruncDay
    elif bucket_size == 7:
        trunc_func = TruncWeek
    elif bucket_size == 30:
        trunc_func = TruncMonth
    else:
        return Response({
            "msg": "Bucket size not supported. Only 1, 7, & 30 days are supported"
        }, status=400)
    
    # Calculate the count of users who joined before the start_date
    pre_start_date_count = queryset.filter(date_joined__lt=start_date).count()

    user_counts = (queryset.filter(date_joined__range=[start_date, end_date])
                   .annotate(bucket=trunc_func('date_joined'))
                   .values('bucket')
                   .annotate(count=Count('id'))
                   .order_by('bucket'))

    if cumulative:
        cumulative_count = pre_start_date_count
        data = []
        for stats in user_counts:
            cumulative_count += stats['count']
            data.append({'date': stats['bucket'], 'count': cumulative_count})
    else:
        data = [{'date': stats['bucket'], 'count': stats['count']} for stats in user_counts]

    return Response(data)

@extend_schema(
    request=inline_serializer(
        name='MessageStatisticsCountOverTimeRequest',
        fields={
            'bucket_size': serializers.IntegerField(default=1),
            'base_list': serializers.ChoiceField(
                choices=[entry.name for entry in FILTER_LISTS],
                default='all',
            ),
            'start_date': serializers.DateField(default='2022-01-01'),
            'end_date': serializers.DateField(default=date.today())
        }
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def message_statistics(request):
    # Validate the inputs
    today = date.today()
    bucket_size = request.data.get('bucket_size', 1)
    
    start_date = request.data.get('start_date', '2022-01-01')
    end_date = request.data.get('end_date', today)

    list_name = request.data.get('base_list', 'all')
    selected_filter = next(filter(lambda entry: entry.name == list_name, FILTER_LISTS))

    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())

    queryset = selected_filter.queryset(qs=pre_filtered_users)

    if bucket_size == 1:
        trunc_func = TruncDay
    elif bucket_size == 7:
        trunc_func = TruncWeek
    elif bucket_size == 30:
        trunc_func = TruncMonth
    else:
        return Response({
            "msg": "Bucket size not supported only 1 & 7 days are supported"
        }, status=400)
    
    message_queryset = (Message.objects.filter(
                            sender__in=queryset, 
                            recipient__in=queryset,
                            created__range=[start_date, end_date])
                        .annotate(bucket=trunc_func('created'))
                        .values('bucket')
                        .annotate(count=Count('id'))
                        .order_by('bucket'))

    data = [{'date': stats['bucket'], 'count': stats['count']} for stats in message_queryset]

    return Response(data)


@extend_schema(
    request=inline_serializer(
        name='LivekitSessionStatisticsCountOverTimeRequest',
        fields={
            'bucket_size': serializers.IntegerField(default=1),
            'base_list': serializers.ChoiceField(
                choices=[entry.name for entry in FILTER_LISTS],
                default='all',
            ),
            'start_date': serializers.DateField(default='2022-01-01'),
            'end_date': serializers.DateField(default=date.today()),
        }
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def livekit_session_statistics(request):
    # Validate the inputs
    today = date.today()
    bucket_size = request.data.get('bucket_size', 1)

    min_start_date = date(2024, 4, 4)
    start_date = request.data.get('start_date', f'{min_start_date}')
    if start_date < f'{min_start_date}':
        start_date = f'{min_start_date}'

    end_date = request.data.get('end_date', today)

    list_name = request.data.get('base_list', 'all')
    selected_filter = next(filter(lambda entry: entry.name == list_name, FILTER_LISTS))

    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())

    queryset = selected_filter.queryset(qs=pre_filtered_users)
    
    aggregation = request.query_params.get('aggregation', 'count')

    if bucket_size == 1:
        trunc_func = TruncDay
    elif bucket_size == 7:
        trunc_func = TruncWeek
    elif bucket_size == 30:
        trunc_func = TruncMonth
    else:
        return Response({
            "msg": "Bucket size not supported only 1 & 7 days are supported"
        }, status=400)
    
    livekit_queryset = LivekitSession.objects.filter(
        u1__in=queryset,
        u2__in=queryset,
        both_have_been_active=True,
        created_at__range=[start_date, end_date]
    ).annotate(bucket=trunc_func('created_at'))

    if aggregation == 'count':
        livekit_queryset = livekit_queryset.values('bucket').annotate(count=Count('id')).order_by('bucket')
        data = [{'date': stats['bucket'], 'count': stats['count']} for stats in livekit_queryset]
    elif aggregation == 'total_time':
        livekit_queryset = livekit_queryset.values('bucket').annotate(
            total_time=Sum(F('end_time') - F('created_at'))
        ).order_by('bucket')
        data = [{'date': stats['bucket'], 'count': stats['total_time'].total_seconds() / 60.0} for stats in livekit_queryset]
    elif aggregation == 'average_time':
        livekit_queryset = livekit_queryset.values('bucket').annotate(
            average_time=Avg(F('end_time') - F('created_at'))
        ).order_by('bucket')
        data = [{'date': stats['bucket'], 'count': stats['average_time'].total_seconds() / 60.0} for stats in livekit_queryset]
    else:
        return Response({
            "msg": "Aggregation type not supported."
        }, status=400)

    return Response(data)

@extend_schema(
    request=inline_serializer(
        name='BucketStatisticsCountOverTimeRequest',
        fields={
            'selected_filters': serializers.ListField(
                child=serializers.ChoiceField(
                    choices=[entry.name for entry in USER_JOURNEY_FILTER_LISTS],
                ),
                required=True
            ),
            'start_date': serializers.DateField(default='2021-01-01', required=False),
            'end_date': serializers.DateField(default=date.today(), required=False)
        }
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def bucket_statistics(request):
    today = date.today()

    start_date = request.data.get('start_date', '2022-01-01')
    end_date = request.data.get('end_date', today)

    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())
    
    pre_filtered_users = pre_filtered_users.filter(date_joined__range=[start_date, end_date])
    
    selected_filters = request.data.get('selected_filters', None)
    
    if selected_filters is None:
        selected_filters = [entry.name for entry in FILTER_LISTS]
        
        
    user_buckets = []
    selected_filters_list = [entry for entry in FILTER_LISTS if entry.name in selected_filters]
    for filter_list in selected_filters_list:
        queryset = filter_list.queryset(qs=pre_filtered_users)
        count = queryset.count()
        user_buckets.append({
            'name': filter_list.name,
            'description': filter_list.description,
            'count': count
        })
        
    return Response(user_buckets)

@extend_schema(
    request=inline_serializer(
        name='MatchBucketStatisticsCountOverTimeRequest',
        fields={
            'selected_filters': serializers.ListField(
                child=serializers.ChoiceField(
                    choices=[entry.name for entry in MATCH_JOURNEY_FILTERS],
                ),
                required=True
            ),
            'start_date': serializers.DateField(default='2021-01-01', required=False),
            'end_date': serializers.DateField(default=date.today(), required=False)
        }
    ),
)
@api_view(['POST'])
@permission_classes([IsAdminOrMatchingUser])
def match_bucket_statistics(request):
    today = date.today()

    start_date = request.data.get('start_date', '2022-01-01')
    end_date = request.data.get('end_date', today)

    pre_filtered_users = User.objects.all()
    if not request.user.is_staff:
        pre_filtered_users = pre_filtered_users.filter(id__in=request.user.state.managed_users.all())
    
    pre_filtered_matches = Match.objects.filter(
        Q(user1__in=pre_filtered_users) | Q(user2__in=pre_filtered_users),
        created_at__range=[start_date, end_date]
    )
    
    selected_filters = request.data.get('selected_filters', None)
    
    if selected_filters is None:
        selected_filters = [entry.name for entry in MATCH_JOURNEY_FILTERS]
        
        
    match_buckets = []
    selected_filters_list = [entry for entry in MATCH_JOURNEY_FILTERS if entry.name in selected_filters]
    for filter_list in selected_filters_list:
        queryset = filter_list.queryset(qs=pre_filtered_matches)
        count = queryset.count()
        match_buckets.append({
            'name': filter_list.name,
            'description': filter_list.description,
            'count': count
        })
        
    return Response(match_buckets)
        

api_urls = [
    path('api/matching/users/statistics/signups/', user_signups),
    path('api/matching/users/statistics/messages_send/', message_statistics),
    path('api/matching/users/statistics/video_calls/', livekit_session_statistics),
    path('api/matching/users/statistics/user_journey_buckets/', bucket_statistics),
    path('api/matching/users/statistics/match_journey_buckets/', match_bucket_statistics),
]