import pytest

ORGANIZATIONS_URL = "/api/v2/organizations/"


@pytest.mark.django_db
class TestOrganizationVisibility:
    def test_a_user_sees_only_their_own_organization(
        self, authenticated_client, organization, other_organization
    ):
        response = authenticated_client.get(ORGANIZATIONS_URL)

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(organization.id)

    def test_retrieving_another_organization_is_a_404(
        self, authenticated_client, other_organization
    ):
        response = authenticated_client.get(f"{ORGANIZATIONS_URL}{other_organization.id}/")

        assert response.status_code == 404

    def test_platform_staff_see_every_organization(
        self, platform_client, organization, other_organization
    ):
        response = platform_client.get(ORGANIZATIONS_URL)

        assert response.data["count"] == 2

    def test_anonymous_request_is_rejected(self, api_client):
        response = api_client.get(ORGANIZATIONS_URL)

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestOrganizationSettings:
    def test_an_admin_can_change_organization_settings(self, admin_client, organization):
        response = admin_client.patch(
            f"{ORGANIZATIONS_URL}{organization.id}/", {"name": "Kipchi Ltd"}, format="json"
        )

        assert response.status_code == 200, response.data
        organization.refresh_from_db()
        assert organization.name == "Kipchi Ltd"

    def test_a_manager_cannot_change_organization_settings(
        self, manager_client, organization
    ):
        """A MANAGER runs shops; renaming the business is not theirs to do."""
        response = manager_client.patch(
            f"{ORGANIZATIONS_URL}{organization.id}/", {"name": "Hijacked"}, format="json"
        )

        assert response.status_code == 403
        organization.refresh_from_db()
        assert organization.name == "Kipchi Supermarket"

    def test_a_cashier_cannot_change_organization_settings(
        self, authenticated_client, organization
    ):
        response = authenticated_client.patch(
            f"{ORGANIZATIONS_URL}{organization.id}/", {"name": "Hijacked"}, format="json"
        )

        assert response.status_code == 403
        organization.refresh_from_db()
        assert organization.name == "Kipchi Supermarket"

    def test_the_slug_is_not_client_editable(self, admin_client, organization):
        response = admin_client.patch(
            f"{ORGANIZATIONS_URL}{organization.id}/", {"slug": "taken-over"}, format="json"
        )

        assert response.status_code == 200
        organization.refresh_from_db()
        assert organization.slug == "kipchi"

    def test_organizations_cannot_be_created_through_the_api(self, admin_client):
        """Creating a tenant is a platform-operator action, done in the admin."""
        response = admin_client.post(
            ORGANIZATIONS_URL,
            {"name": "Shadow Shop", "slug": "shadow-shop"},
            format="json",
        )

        assert response.status_code == 405
