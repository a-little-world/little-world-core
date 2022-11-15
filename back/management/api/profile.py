from rest_framework import viewsets, authentication, permissions
from ..models import SelfProfileSerializer, Profile


class ProfileViewSet(viewsets.GenericViewSet, viewsets.mixins.UpdateModelMixin):
    """
    A viewset for viewing and editing user instances.
    """
    authentication_classes = [authentication.SessionAuthentication,
                              authentication.BasicAuthentication]

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = SelfProfileSerializer

    def get_object(self):
        return self.get_queryset()[0]

    def partial_update(self, request, pk=None):
        #assert not pk
        pk = self.request.user.pk
        self.kwargs["pk"] = 1
        return super().partial_update(request, pk=pk)

    def get_queryset(self):
        user = self.request.user
        return [getattr(user, "profile")]
