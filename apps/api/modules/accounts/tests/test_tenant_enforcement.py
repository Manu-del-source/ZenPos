"""Suspended tenants and deactivated accounts stop at the boundary.

``Organization.is_active`` and ``User.is_active`` are switches, and a switch
that nothing reads is a decoration. Flipping either one has to cut access in
three places at once — login (no new tokens), refresh (no extended sessions)
and every API call (a held access token dies) — and restoring it has to put
everything back.
"""

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/v2/auth/login/"
REFRESH_URL = "/api/v2/auth/refresh/"
USERS_URL = "/api/v2/users/"


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _login(client, username, password="test-password-1"):
    return client.post(LOGIN_URL, {"username": username, "password": password}, format="json")


class TestTenantSuspension:
    def test_an_active_tenant_logs_in_and_refreshes(self, cashier):
        """The control: none of the new checks may block a healthy tenant."""
        client = APIClient()
        login = _login(client, cashier.username)
        assert login.status_code == 200, login.data
        assert (
            client.post(REFRESH_URL, {"refresh": login.data["refresh"]}, format="json").status_code
            == 200
        )

    def test_a_suspended_tenant_cannot_log_in(self, cashier, organization):
        organization.is_active = False
        organization.save(update_fields=["is_active"])

        response = _login(APIClient(), cashier.username)

        assert response.status_code == 401
        assert "suspended" in str(response.data)

    def test_a_suspended_tenant_cannot_refresh(self, cashier, organization):
        client = APIClient()
        login = _login(client, cashier.username)
        assert login.status_code == 200, login.data

        organization.is_active = False
        organization.save(update_fields=["is_active"])

        response = client.post(REFRESH_URL, {"refresh": login.data["refresh"]}, format="json")
        assert response.status_code == 401

    def test_a_suspended_tenant_cannot_call_the_api_with_a_held_token(
        self, authenticated_client, organization
    ):
        """The access token a cashier already holds is not a get-out-of-jail-free."""
        organization.is_active = False
        organization.save(update_fields=["is_active"])

        response = authenticated_client.get("/api/v2/auth/me/")
        assert response.status_code == 403

    def test_activating_the_tenant_restores_access(self, cashier, organization):
        organization.is_active = False
        organization.save(update_fields=["is_active"])
        organization.is_active = True
        organization.save(update_fields=["is_active"])

        assert _login(APIClient(), cashier.username).status_code == 200


class TestDeactivatedUser:
    def test_a_deactivated_user_cannot_log_in(self, manager_client, cashier):
        response = manager_client.patch(
            f"{USERS_URL}{cashier.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 200, response.data

        assert _login(APIClient(), cashier.username).status_code == 401

    def test_a_deactivated_user_cannot_refresh_or_call_the_api(self, manager_client, cashier):
        client = APIClient()
        login = _login(client, cashier.username)
        assert login.status_code == 200, login.data

        response = manager_client.patch(
            f"{USERS_URL}{cashier.pk}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 200, response.data

        # A real request re-reads the user from the database, as JWT
        # authentication does; force_authenticate does not, so mirror it.
        cashier.refresh_from_db()
        held_token_client = _client_for(cashier)

        # The session the user already holds is over: no extension, no calls.
        assert (
            client.post(REFRESH_URL, {"refresh": login.data["refresh"]}, format="json").status_code
            == 401
        )
        assert held_token_client.get("/api/v2/auth/me/").status_code == 403

    def test_reactivating_the_user_restores_access(self, manager_client, cashier):
        manager_client.patch(f"{USERS_URL}{cashier.pk}/", {"is_active": False}, format="json")
        manager_client.patch(f"{USERS_URL}{cashier.pk}/", {"is_active": True}, format="json")

        assert _login(APIClient(), cashier.username).status_code == 200


class TestPlatformAccounts:
    def test_a_deactivated_platform_account_is_blocked(self, platform_admin):
        """Platform staff belong to no organization, but the user switch still applies."""
        platform_admin.is_active = False
        platform_admin.save(update_fields=["is_active"])

        response = _client_for(platform_admin).get("/api/v2/organizations/")
        assert response.status_code == 403

    def test_suspending_a_tenant_does_not_touch_the_platform(self, platform_client, organization):
        organization.is_active = False
        organization.save(update_fields=["is_active"])

        response = platform_client.get("/api/v2/organizations/")
        assert response.status_code == 200
        rows = {row["id"]: row for row in response.data["results"]}
        assert rows[str(organization.id)]["is_active"] is False
