from django.urls import path, include
from patenmatch.models import PatenmatchUser, PatenmatchOrganization
from rest_framework import routers, serializers, viewsets, permissions
from translations import get_translation
from django_filters import rest_framework as filters
from django_filters.rest_framework import DjangoFilterBackend
from management.helpers.is_admin_or_matching_user import IsAdminOrMatchingUser
from management.helpers.detailed_pagination import DetailedPagination
import pgeocode
from rest_framework.filters import OrderingFilter


class PatenmatchUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatenmatchUser
        fields = ["first_name", "last_name", "postal_code", "email", "support_for"]

    def validate_email(self, value):
        if PatenmatchUser.objects.filter(email=value).exists():
            raise serializers.ValidationError(get_translation("patenmatch.user.email.exists", lang="de"))
        return value


class PatenmatchOrganizationSerializer(serializers.ModelSerializer):
    target_groups = serializers.ListField(child=serializers.CharField(), write_only=True)

    class Meta:
        model = PatenmatchOrganization
        fields = ["name", "postal_code", "contact_first_name", "contact_second_name", "contact_email", "contact_phone", "maximum_distance", "capacity", "target_groups", "logo_url", "website_url", "matched_users", "metadata"]

    def create(self, validated_data):
        target_groups = validated_data.pop("target_groups", [])
        validated_data["target_groups"] = ",".join(target_groups)

        return super().create(validated_data)

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.target_groups:
            representation["target_groups"] = instance.target_groups
        return representation


class PatenmatchOrganizationFilter(filters.FilterSet):
    postal_code = filters.CharFilter(method="filter_postal_code")
    target_groups = filters.CharFilter(method="filter_target_groups")
    pg_instance = pgeocode.GeoDistance("DE")

    class Meta:
        model = PatenmatchOrganization
        fields = ["target_groups", "postal_code"]

    def filter_target_groups(self, queryset, name, value):
        target_group_values = value.split(",")
        for target in target_group_values:
            queryset = queryset.filter(target_groups__contains=target)
        return queryset

    def filter_postal_code(self, queryset, name, value):
        matching_ids = []

        for entry in queryset:
            postal_codes_org = entry.postal_code.replace(" ", "").split(",")
            for pco in postal_codes_org:
                if self.pg_instance.query_postal_code(value, pco) <= entry.maximum_distance:
                    matching_ids.append(entry.id)
                    break

        return queryset.filter(id__in=matching_ids)


class PatenmatchUserViewSet(viewsets.ModelViewSet):
    queryset = PatenmatchUser.objects.all()
    serializer_class = PatenmatchUserSerializer
    http_method_names = ["post"]

    def create(self, request, *args, **kwargs):
        res = super().create(request, *args, **kwargs)
        patenmatch_user = PatenmatchUser.objects.get(email=request.data["email"])
        
        # If the creation or anything else throw an error we will not get here
        # But all this is quite magical so in the future we might want to move this to an '@action' and do some more implicit logic
        from management.tasks import send_email_background

        send_email_background.delay("patenmatch-signup", user_id=patenmatch_user.id, patenmatch=True)
        
        return res


class PatenmatchOrganizationViewSet(viewsets.ModelViewSet):
    queryset = PatenmatchOrganization.objects.all()
    serializer_class = PatenmatchOrganizationSerializer
    pagination_class = DetailedPagination
    http_method_names = ["post", "get"]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = PatenmatchOrganizationFilter
    ordering_fields = ["name"]  # Specify which fields can be ordered
    ordering = ["name"]

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAuthenticated(), IsAdminOrMatchingUser()]
        return [permissions.AllowAny()]


router = routers.DefaultRouter()
router.register(r"user", PatenmatchUserViewSet)
router.register(r"organization", PatenmatchOrganizationViewSet)

urlpatterns = [
    path("", include(router.urls)),
]
