"""The platform surface: onboarding and the tenant switch.

Opening a tenant and closing one are platform-operator actions, never tenant
self-service. A tenant that could create or suspend itself could lock itself
out with no way back, or open a rival shop's data surface under its own
name.
"""

import pytest
from rest_framework.test import APIClient

from modules.accounts.models import User
from modules.core.models import AuditLog
from modules.organizations.models import Organization

pytestmark = pytest.mark.django_db

PLATFORM_ORGS_URL = "/api/v2/platform/organizations/"
LOGIN_URL = "/api/v2/auth/login/"
USERS_ORG_URL = "/api/v2/organizations/"

ONBOARD_PAYLOAD = {
    "name": "Savannah Traders",
    "branch_name": "Nakuru",
    "branch_code": "NAK-001",
    "admin_username": "savannah-admin",
    "admin_password": "savannah-opens-100",
}


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestOnboarding:
    def test_onboarding_creates_a_working_tenant(self, platform_client):
        response = platform_client.post(PLATFORM_ORGS_URL, ONBOARD_PAYLOAD, format="json")

        assert response.status_code == 201, response.data
        organization = Organization.objects.get(slug="savannah-traders")
        assert response.data["slug"] == "savannah-traders"
        assert organization.branches.count() == 1
        assert organization.branches.first().code == "NAK-001"

        admin = User.objects.get(username="savannah-admin")
        assert admin.organization_id == organization.pk
        assert "ADMIN" in admin.role_names()
        assert AuditLog.objects.filter(action="organization.created").exists()

        # The new administrator can sign in and reaches their shop.
        client = APIClient()
        login = client.post(
            LOGIN_URL,
            {"username": "savannah-admin", "password": ONBOARD_PAYLOAD["admin_password"]},
            format="json",
        )
        assert login.status_code == 200, login.data
        client.credentials(**{"HTTP_AUTHORIZATION": f"Bearer {login.data['access']}"})
        me = client.get("/api/v2/auth/me/")
        assert me.status_code == 200
        assert me.data["organization"] == str(organization.pk)
        assert "customers.manage" in me.data["permissions"]

    def test_the_slug_defaults_from_the_name(self, platform_client):
        payload = {**ONBOARD_PAYLOAD, "name": "Kikuyu Grocers Ltd", "slug": ""}
        response = platform_client.post(PLATFORM_ORGS_URL, payload, format="json")
        assert response.status_code == 201, response.data
        assert response.data["slug"] == "kikuyu-grocers-ltd"

    def test_a_taken_slug_is_a_400(self, platform_client, organization):
        payload = {**ONBOARD_PAYLOAD, "slug": organization.slug}
        response = platform_client.post(PLATFORM_ORGS_URL, payload, format="json")
        assert response.status_code == 400
        assert "slug" in response.data

    def test_a_taken_username_is_a_400(self, platform_client, cashier):
        payload = {**ONBOARD_PAYLOAD, "admin_username": cashier.username}
        response = platform_client.post(PLATFORM_ORGS_URL, payload, format="json")
        assert response.status_code == 400
        assert "admin_username" in response.data

    def test_a_weak_password_is_a_400(self, platform_client):
        payload = {**ONBOARD_PAYLOAD, "admin_password": "short"}
        response = platform_client.post(PLATFORM_ORGS_URL, payload, format="json")
        assert response.status_code == 400
        assert "admin_password" in response.data

    def test_onboarding_leaves_no_half_tenant_on_validation_failure(
        self, platform_client, organization
    ):
        before = Organization.objects.count()
        response = platform_client.post(
            PLATFORM_ORGS_URL, {**ONBOARD_PAYLOAD, "slug": organization.slug}, format="json"
        )
        assert response.status_code == 400
        assert Organization.objects.count() == before


class TestPlatformAccess:
    def test_a_tenant_admin_cannot_reach_the_platform_surface(self, admin_client, organization):
        assert (
            admin_client.post(PLATFORM_ORGS_URL, ONBOARD_PAYLOAD, format="json").status_code == 403
        )
        assert (
            admin_client.post(f"{PLATFORM_ORGS_URL}{organization.id}/suspend/").status_code == 403
        )

    def test_another_tenant_admin_cannot_suspend_a_rival(
        self, api_client, rival_user, organization
    ):
        """The platform surface is superuser-only; a rival manager is not a platform staff."""
        client = _client_for(rival_user)
        assert client.post(f"{PLATFORM_ORGS_URL}{organization.id}/suspend/").status_code == 403

    def test_anonymous_is_rejected(self, api_client):
        assert api_client.post(PLATFORM_ORGS_URL, ONBOARD_PAYLOAD, format="json").status_code in (
            401,
            403,
        )


class TestTenantSwitch:
    def test_suspending_a_tenant_locks_it_out_and_is_audited(
        self, platform_client, organization, cashier
    ):
        response = platform_client.post(f"{PLATFORM_ORGS_URL}{organization.id}/suspend/")

        assert response.status_code == 200, response.data
        organization.refresh_from_db()
        assert organization.is_active is False
        assert AuditLog.objects.filter(
            action="organization.suspended", entity_id=str(organization.pk)
        ).exists()

        login = APIClient().post(
            LOGIN_URL,
            {"username": cashier.username, "password": "test-password-1"},
            format="json",
        )
        assert login.status_code == 401

    def test_activating_a_tenant_puts_it_back(self, platform_client, organization, cashier):
        platform_client.post(f"{PLATFORM_ORGS_URL}{organization.id}/suspend/")
        response = platform_client.post(f"{PLATFORM_ORGS_URL}{organization.id}/activate/")
        assert response.status_code == 200, response.data
        organization.refresh_from_db()
        assert organization.is_active is True

        login = APIClient().post(
            LOGIN_URL,
            {"username": cashier.username, "password": "test-password-1"},
            format="json",
        )
        assert login.status_code == 200

    def test_flipping_a_switch_that_is_already_set_is_refused(self, platform_client, organization):
        response = platform_client.post(f"{PLATFORM_ORGS_URL}{organization.id}/suspend/")
        assert response.status_code == 200

        repeat = platform_client.post(f"{PLATFORM_ORGS_URL}{organization.id}/suspend/")
        assert repeat.status_code == 400

    def test_a_tenant_cannot_suspend_itself_through_the_profile(self, admin_client, organization):
        """``is_active`` is not tenant-writable; the switch belongs to the platform."""
        response = admin_client.patch(
            f"{USERS_ORG_URL}{organization.id}/", {"is_active": False}, format="json"
        )
        assert response.status_code == 200
        organization.refresh_from_db()
        assert organization.is_active is True

    def test_suspending_a_rival_is_invisible_to_the_tenant(
        self, platform_client, cashier, other_organization
    ):
        """A tenant cannot even tell that a rival was suspended: it is a 404, not a 403."""
        response = platform_client.post(f"{PLATFORM_ORGS_URL}{other_organization.id}/suspend/")
        assert response.status_code == 200

        # (Two *_client fixtures would share one underlying client, so the
        # tenant side is built explicitly.)
        read = _client_for(cashier).get(f"{USERS_ORG_URL}{other_organization.id}/")
        assert read.status_code == 404
