from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from management.api.matches_advanced import AdvancedMatchViewset
from management.models.matches import Match
from management.tests.helpers import register_user


class AdvancedMatchViewsetTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory(enforce_csrf_checks=True)
        self.view = AdvancedMatchViewset.as_view({"get": "retrieve"})

        self.staff_user = register_user()
        self.staff_user.is_staff = True
        self.staff_user.save(update_fields=["is_staff"])

        self.other_user = register_user()
        self.match = Match.objects.create(user1=self.staff_user, user2=self.other_user)

    def test_retrieve_existing_match_by_uuid(self):
        request = self.factory.get(f"/api/matching/matches/{self.match.uuid}/")
        force_authenticate(request, user=self.staff_user)

        response = self.view(request, pk=str(self.match.uuid))

        assert response.status_code == 200
        assert response.data["uuid"] == str(self.match.uuid)

    def test_retrieve_unknown_match_by_uuid_returns_404(self):
        missing_uuid = uuid4()
        request = self.factory.get(f"/api/matching/matches/{missing_uuid}/")
        force_authenticate(request, user=self.staff_user)

        response = self.view(request, pk=str(missing_uuid))

        assert response.status_code == 404
