from django.urls import path, include
from rest_framework import routers, serializers, viewsets, permissions
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
