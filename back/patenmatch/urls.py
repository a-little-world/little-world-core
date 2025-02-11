from django.urls import include, path
from rest_framework import permissions, routers, serializers, viewsets

from patenmatch.api import PatenmatchOrganizationViewSet, PatenmatchUserViewSet

router = routers.DefaultRouter()
router.register(r"organization", PatenmatchOrganizationViewSet)

urlpatterns = [
    path("", include(router.urls)),
    # Expplictly expose user apis, as otherwise with "get" in http_method_names it will try to also register user/<pk/retrieve
    path("user/verify_email/", PatenmatchUserViewSet.as_view({"get": "verify_email"})),
    path("user/", PatenmatchUserViewSet.as_view({"post": "create"})),
    path("user/<int:pk>/status/", PatenmatchUserViewSet.as_view({"get": "status"})),
]
