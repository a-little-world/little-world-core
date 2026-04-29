from uuid import uuid4

from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from management.api.matches_advanced import AdvancedMatchViewset
from management.models.matches import Match
from management.models.user import User


class AdvancedMatchViewsetTests(TestCase):
    def _create_user(self, email_prefix: str) -> User:
        return User.objects.create_user(
            email=f"{email_prefix}-{uuid4()}@example.com",
            password="Test123!",
            first_name="Test",
            last_name="User",
        )

    def setUp(self):
        self.factory = APIRequestFactory(enforce_csrf_checks=True)
        self.view = AdvancedMatchViewset.as_view({"get": "retrieve"})
        self.list_view = AdvancedMatchViewset.as_view({"get": "list"})
        self.export_view = AdvancedMatchViewset.as_view({"get": "export"})

        self.staff_user = self._create_user("staff")
        self.staff_user.is_staff = True
        self.staff_user.save(update_fields=["is_staff"])

        self.other_user = self._create_user("other")
        self.match = Match.objects.create(user1=self.staff_user, user2=self.other_user)
        self.off_platform_match = Match.objects.create(
            user1=self.staff_user,
            user2=self._create_user("other-off-platform"),
            completed_off_plattform=True,
        )

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

    def test_list_filter_match_completed_off_plattform_returns_only_marked_matches(self):
        request = self.factory.get("/api/matching/matches/?list=match_completed_off_plattform")
        force_authenticate(request, user=self.staff_user)

        response = self.list_view(request)

        assert response.status_code == 200
        results = response.data["results"]
        returned_uuids = {item["uuid"] for item in results}
        assert str(self.off_platform_match.uuid) in returned_uuids
        assert str(self.match.uuid) not in returned_uuids

    def test_export_includes_completed_off_plattform_field(self):
        request = self.factory.get("/api/matching/matches_export/?list=match_completed_off_plattform")
        force_authenticate(request, user=self.staff_user)

        response = self.export_view(request)

        assert response.status_code == 200
        assert len(response.data) == 1
        exported_match = response.data[0]
        assert "completed_off_plattform" in exported_match
        assert exported_match["completed_off_plattform"] is True
