"""Shared response serializers for management API OpenAPI documentation."""

from rest_framework import serializers

from management.models.support_task import SupportTaskListSerializer


class DetailedPaginatedResponseSerializer(serializers.Serializer):
    page_size = serializers.IntegerField()
    pages_total = serializers.IntegerField()
    items_total = serializers.IntegerField()
    results_total = serializers.IntegerField(required=False)
    page = serializers.IntegerField(required=False)
    first_page = serializers.IntegerField(required=False)
    last_page = serializers.IntegerField(required=False)
    next_page = serializers.IntegerField(required=False, allow_null=True)
    previous_page = serializers.IntegerField(required=False, allow_null=True)
    count = serializers.IntegerField(required=False)
    next = serializers.CharField(required=False, allow_null=True)
    previous = serializers.CharField(required=False, allow_null=True)


class PaginatedSupportTaskResponse(DetailedPaginatedResponseSerializer):
    results = SupportTaskListSerializer(many=True)


class SupportTaskStatsSerializer(serializers.Serializer):
    NEW = serializers.IntegerField()
    IN_PROGRESS = serializers.IntegerField()
    COMPLETED = serializers.IntegerField()


class SupportTaskUserSearchEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    second_name = serializers.CharField()


class SupportAssigneeUserEntrySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class SupportTaskOpenCountSerializer(serializers.Serializer):
    count = serializers.IntegerField()
