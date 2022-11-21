from rest_framework import viewsets, authentication, permissions
from ..models import SelfProfileSerializer, Profile
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample
from rest_framework.views import APIView
from rest_framework import serializers
from dataclasses import dataclass
from back.utils import transform_add_options_serializer


@dataclass
class ProfileViewSetParams:
    options: bool = False


class ProfileViewSetSerializer(serializers.Serializer):
    options = serializers.BooleanField(required=False)

    def create(self, validated_data):
        return ProfileViewSetParams(**validated_data)  # type: ignore


class ProfileViewSet(viewsets.GenericViewSet, viewsets.mixins.UpdateModelMixin):
    """
    A viewset for viewing and editing user instances.
    """
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SelfProfileSerializer

    @extend_schema(
        request=ProfileViewSetSerializer(many=False),
        parameters=[
            OpenApiParameter(name=k, description="Use this and every self field will contain possible choices in 'options'" if k == "options" else "",
                             required=False, type=type(getattr(ProfileViewSetParams, k)))
            for k in ProfileViewSetParams.__annotations__.keys()
        ],
    )
    def _get(self, request):
        serializer = ProfileViewSetSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        params = serializer.save()

        _s = SelfProfileSerializer
        if params.options:
            _s = transform_add_options_serializer(_s)

        return Response(_s(getattr(self.request.user, "profile")).data)

    def get_object(self):
        return self.get_queryset()[0]

    def partial_update(self, request, pk=None):
        #assert not pk
        pk = self.request.user.pk
        self.kwargs["pk"] = 1
        print("request.data" + str(request.data))
        return super().partial_update(request, pk=pk)

    def get_queryset(self):
        user = self.request.user
        return [getattr(user, "profile")]
