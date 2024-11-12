from django.urls import path, include
from patenmatch.models import PatenmatchUser, PatenmatchOrganization
from rest_framework import routers, serializers, viewsets, permissions, status
from rest_framework.response import Response
from translations import get_translation
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from management.helpers.is_admin_or_matching_user import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import DetailedPagination


class PatenmatchUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatenmatchUser
        fields = ["first_name", "last_name", "postal_code", "email", "support_for"]

    def validate_email(self, value):
        if PatenmatchUser.objects.filter(email=value).exists():
            raise serializers.ValidationError(get_translation("patenmatch.user.email.exists", lang="de"))
        return value


class PatenmatchOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatenmatchOrganization
        fields = ["name", "postal_code", "contact_first_name", "contact_second_name", "contact_email", "contact_phone", "maximum_distance", "capacity", "target_groups", "logo_url", "website_url", "matched_users", "metadata"]


class PatenmatchOrganizationFilter(filters.FilterSet):
    target_groups = filters.CharFilter(method="filter_target_groups")

    class Meta:
        model = PatenmatchOrganization
        fields = ["postal_code", "target_groups"]

    def filter_target_groups(self, queryset, name, value):
        target_group_values = value.split(",")
        for target in target_group_values:
            queryset = queryset.filter(target_groups__contains=target)
        return queryset


class PatenmatchUserViewSet(viewsets.ModelViewSet):
    queryset = PatenmatchUser.objects.all()
    serializer_class = PatenmatchUserSerializer
    http_method_names = ["post"]


class PatenmatchOrganizationViewSet(viewsets.ModelViewSet):
    # class CustomPagination(PageNumberPagination):
    #    page_size = 10
    #    page_size_query_param = "page_size"
    #    max_page_size = 100
    #
    #    def get_paginated_response(self, data):
    #        return response.Response({"count": self.page.paginator.count, "total_pages": self.page.paginator.num_pages, "current_page": self.page.number, "next": self.get_next_link(), "previous": self.get_previous_link(), "results": data})

    queryset = PatenmatchOrganization.objects.all()
    serializer_class = PatenmatchOrganizationSerializer
    pagination_class = DetailedPagination
    http_method_names = ["post", "get"]
    filter_backends = [DjangoFilterBackend]
    filterset_class = PatenmatchOrganizationFilter

    def list(self, request, *args, **kwargs):
        postal_code = request.query_params.get("postal_code", None)
        if postal_code is None or postal_code.strip() == "":
            return Response({"detail": "postal_code is required for this request."}, status=status.HTTP_400_BAD_REQUEST)

        return super().list(request, *args, **kwargs)

    def get_permissions(self):
        if self.action == "create":  # This action corresponds to POST requests
            return [permissions.IsAuthenticated(), IsAdminOrMatchingUser()]
        return [permissions.AllowAny()]


router = routers.DefaultRouter()
router.register(r"user", PatenmatchUserViewSet)
router.register(r"organization", PatenmatchOrganizationViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
