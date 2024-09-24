from django.urls import path, include
from patenmatch.models import PatenmatchUser, PatenmatchOrganization
from rest_framework import routers, serializers, viewsets, response
from rest_framework.pagination import PageNumberPagination


class PatenmatchUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatenmatchUser
        fields = ["first_name", "last_name", "postal_code", "email", "support_for"]


class PatenmatchOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatenmatchOrganization
        fields = ["name", "postal_code", "contact_first_name", "contact_second_name", "contact_email", "contact_phone", "maximum_distance", "capacity", "target_groups", "logo_url", "website_url", "matched_users", "metadata"]


class PatenmatchUserViewSet(viewsets.ModelViewSet):
    queryset = PatenmatchUser.objects.all()
    serializer_class = PatenmatchUserSerializer
    http_method_names = ["post"]


class PatenmatchOrganizationViewSet(viewsets.ModelViewSet):
    class CustomPagination(PageNumberPagination):
        page_size = 10
        page_size_query_param = "page_size"
        max_page_size = 100

        def get_paginated_response(self, data):
            return response.Response({"count": self.page.paginator.count, "total_pages": self.page.paginator.num_pages, "current_page": self.page.number, "next": self.get_next_link(), "previous": self.get_previous_link(), "results": data})

    queryset = PatenmatchOrganization.objects.all()
    serializer_class = PatenmatchOrganizationSerializer
    pagination_class = CustomPagination
    http_method_names = ["post", "get"]
    filterset_fields = {"postal_code": ["exact"], "target_groups": ["contains"]}


router = routers.DefaultRouter()
router.register(r"user", PatenmatchUserViewSet)
router.register(r"organization", PatenmatchOrganizationViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
