import pytest

from modules.accounts.models import UserBranchAccess
from modules.branches.models import Branch

BRANCHES_URL = "/api/v2/branches/"


def branch_payload(**overrides):
    payload = {"name": "Nakuru", "code": "BR-003"}
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestBranchVisibility:
    def test_a_user_posted_to_one_branch_sees_only_that_branch(
        self, supervisor_client, branch, other_branch
    ):
        response = supervisor_client.get(BRANCHES_URL)

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(branch.id)

    def test_a_user_with_no_postings_sees_the_whole_organization(
        self, manager_client, branch, other_branch, foreign_branch
    ):
        """No branch access rows means organization-wide: head office."""
        response = manager_client.get(BRANCHES_URL)

        assert response.data["count"] == 2

    def test_another_organizations_branches_are_invisible(
        self, rival_client, branch, other_branch, foreign_branch
    ):
        response = rival_client.get(BRANCHES_URL)

        assert response.data["count"] == 1
        assert response.data["results"][0]["id"] == str(foreign_branch.id)

    def test_a_user_cannot_open_a_branch_they_are_not_posted_to(
        self, supervisor_client, other_branch
    ):
        response = supervisor_client.get(f"{BRANCHES_URL}{other_branch.id}/")

        assert response.status_code == 404

    def test_the_same_code_may_exist_in_two_organizations(self, branch, foreign_branch):
        assert branch.code == foreign_branch.code
        assert branch.organization_id != foreign_branch.organization_id

    def test_anonymous_request_is_rejected(self, api_client):
        response = api_client.get(BRANCHES_URL)

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestBranchWrites:
    def test_a_cashier_can_read_branches(self, authenticated_client, branch):
        response = authenticated_client.get(BRANCHES_URL)

        assert response.status_code == 200

    def test_a_cashier_cannot_create_a_branch(self, authenticated_client):
        response = authenticated_client.post(BRANCHES_URL, branch_payload(), format="json")

        assert response.status_code == 403
        assert not Branch.objects.filter(code="BR-003").exists()

    def test_a_supervisor_cannot_create_a_branch(self, supervisor_client):
        response = supervisor_client.post(BRANCHES_URL, branch_payload(), format="json")

        assert response.status_code == 403

    def test_a_manager_can_open_a_branch(self, manager_client, organization):
        response = manager_client.post(BRANCHES_URL, branch_payload(), format="json")

        assert response.status_code == 201, response.data
        assert response.data["organization"] == str(organization.id)
        assert Branch.objects.get(code="BR-003").organization_id == organization.id

    def test_a_manager_posted_to_one_branch_can_still_open_another(
        self, api_client, make_user, branch, organization
    ):
        """Opening a branch is not operating in one.

        Branch access governs where a user *works*. A manager who is posted to
        Westlands still has to be able to add the Karen branch, or a second shop
        could never be opened by the person running the first.
        """
        user = make_user("posted-manager", role="MANAGER")
        UserBranchAccess.objects.create(user=user, branch=branch)
        api_client.force_authenticate(user=user)

        response = api_client.post(BRANCHES_URL, branch_payload(), format="json")

        assert response.status_code == 201, response.data

    def test_the_organization_is_never_taken_from_the_payload(
        self, manager_client, organization, other_organization
    ):
        response = manager_client.post(
            BRANCHES_URL,
            branch_payload(organization=str(other_organization.id)),
            format="json",
        )

        assert response.status_code == 201, response.data
        assert Branch.objects.get(code="BR-003").organization_id == organization.id

    def test_a_duplicate_code_in_the_same_organization_is_rejected(
        self, manager_client, branch
    ):
        response = manager_client.post(
            BRANCHES_URL, branch_payload(name="Westlands Two", code=branch.code), format="json"
        )

        assert response.status_code == 400
        assert Branch.objects.count() == 1

    def test_an_existing_branch_can_be_renamed(self, manager_client, branch):
        response = manager_client.patch(
            f"{BRANCHES_URL}{branch.id}/", {"name": "Westlands Mall"}, format="json"
        )

        assert response.status_code == 200
        branch.refresh_from_db()
        assert branch.name == "Westlands Mall"

    def test_a_branch_is_deactivated_rather_than_deleted(self, manager_client, branch):
        """Stock, tills and sales hang off a branch; deleting it destroys history."""
        response = manager_client.delete(f"{BRANCHES_URL}{branch.id}/")

        assert response.status_code == 405
        assert Branch.objects.filter(pk=branch.pk).exists()

    def test_a_branch_can_be_deactivated_by_patching(self, manager_client, branch):
        response = manager_client.patch(
            f"{BRANCHES_URL}{branch.id}/", {"is_active": False}, format="json"
        )

        assert response.status_code == 200
        branch.refresh_from_db()
        assert branch.is_active is False
