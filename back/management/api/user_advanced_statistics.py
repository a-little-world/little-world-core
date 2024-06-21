from rest_framework.decorators import action, api_view, permission_classes
from django.db.models.functions import TruncDay, TruncWeek, ExtractDay
from rest_framework.response import Response
from rest_framework import viewsets
from datetime import timedelta, date
from django.db.models import Q, Count, F
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
    
    bucket_size = 1
    start_date = '2022-01-01'
    end_date = today
    
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
    else:
        return Response({
            "msg": "Bucket size not supported only 1 & 7 days are supported"
        }, status=400)

    user_counts = (queryset.filter(date_joined__range=[start_date, end_date])
                   .annotate(bucket=trunc_func('date_joined'))
                   .values('bucket')
                   .annotate(count=Count('id'))
                   .order_by('bucket'))

    data = [{'date': stats['bucket'], 'count': stats['count']} for stats in user_counts]

    return Response(data)

api_urls = [
    path('api/matching/users/statistics/sign-ups/', user_signups),
]