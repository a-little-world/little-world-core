from uuid import uuid4

from django.conf import settings
from django.test import TestCase
from emails.api.template_lookup import activate_searching_url
from rest_framework.test import APIClient

from management.api.user_advanced import AdvancedUserSerializer
from management.models.state import State
from management.random_test_users import create_test_user


class SearchActivationUrlTests(TestCase):
    def setUp(self):
        self.user = create_test_user(50000, None, "Test123!", "search-activation-url@test.de")

    def test_lookup_contains_uuid_token_and_base_url(self):
        url = activate_searching_url(self.user)

        assert url.startswith(settings.BASE_URL)
        assert str(self.user.uuid) in url
        assert str(self.user.state.search_activation_token) in url

    def test_admin_serializer_exposes_link(self):
        data = AdvancedUserSerializer(self.user).data

        assert data["activate_searching_url"] == activate_searching_url(self.user)


class ActivateSearchingEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_test_user(50001, None, "Test123!", "search-activation-endpoint@test.de")
        self.state = self.user.state
        self.state.unresponsive = True
        self.state.still_active_reminder_confirmed = False
        self.state.searching_state = State.SearchingStateChoices.IDLE
        self.state.save()

    def _url(self, uuid=None, token=None):
        uuid = uuid if uuid is not None else self.user.uuid
        token = token if token is not None else self.state.search_activation_token
        return f"/api/user/activate_searching/{uuid}/{token}/"

    def test_valid_token_activates_searching(self):
        response = self.client.get(self._url())

        assert response.status_code == 200

        self.state.refresh_from_db()
        assert self.state.searching_state == State.SearchingStateChoices.SEARCHING
        assert self.state.unresponsive is False
        assert self.state.still_active_reminder_confirmed is True

    def test_invalid_token_is_rejected_and_state_unchanged(self):
        response = self.client.get(self._url(token=uuid4()))

        assert response.status_code == 403

        self.state.refresh_from_db()
        assert self.state.searching_state == State.SearchingStateChoices.IDLE
        assert self.state.unresponsive is True

    def test_unknown_uuid_renders_failure_card(self):
        response = self.client.get(self._url(uuid=uuid4()))

        assert response.status_code == 200

    def test_malformed_uuid_renders_failure_card(self):
        response = self.client.get("/api/user/activate_searching/not-a-uuid/some-token/")

        assert response.status_code == 200

    def test_already_searching_is_idempotent(self):
        self.state.searching_state = State.SearchingStateChoices.SEARCHING
        self.state.save()

        response = self.client.get(self._url())

        assert response.status_code == 200

        self.state.refresh_from_db()
        assert self.state.searching_state == State.SearchingStateChoices.SEARCHING
