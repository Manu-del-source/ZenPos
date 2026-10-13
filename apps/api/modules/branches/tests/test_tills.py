"""Till management: creation, scoping, permissions, deactivation.

A till is structural tenant data like a branch: it is created and deactivated
by management, read by anyone who can read the branch, and never deleted.
"""

import pytest

from modules.branches.models import Till
from modules.core.models import AuditLog

TILLS_URL = "/api/v2/tills/"


@pytest.mark.django_db
class TestTillManagement:
    def test_manager_creates_till(self, manager_client, organization, branch):
        response = manager_client.post(
            TILLS_URL, {"name": "Till 1", "branch": str(branch.pk)}, format="json"
        )

        assert response.status_code == 201, response.data
        till = Till.objects.get(pk=response.data["id"])
        # The tenant comes from the caller, never from the payload.
        assert till.organization_id == organization.pk
        assert till.branch_id == branch.pk
        assert till.is_active is True

    def test_cashier_cannot_create_till(self, authenticated_client, branch):
        response = authenticated_client.post(
            TILLS_URL, {"name": "Till 1", "branch": str(branch.pk)}, format="json"
        )

        assert response.status_code == 403

    def test_cannot_attach_foreign_organization_branch(self, rival_client, branch):
        # The rival's manager attaches OUR branch to a till in THEIR org: the
        # serializer's organization-bound check refuses the cross-tenant write.
        response = rival_client.post(
            TILLS_URL, {"name": "Till X", "branch": str(branch.pk)}, format="json"
        )

        assert response.status_code == 400
        assert Till.objects.count() == 0

    def test_cannot_read_foreign_organization_till(self, rival_client, till):
        assert rival_client.get(f"{TILLS_URL}{till.pk}/").status_code == 404
        assert rival_client.get(TILLS_URL).data["results"] == []

    def test_cannot_update_foreign_organization_till(self, rival_client, till):
        response = rival_client.patch(
            f"{TILLS_URL}{till.pk}/", {"name": "Hacked"}, format="json"
        )

        assert response.status_code == 404
        till.refresh_from_db()
        assert till.name == "Till 1"

    def test_till_list_is_branch_scoped(
        self, authenticated_client, till, organization, other_branch
    ):
        Till.objects.create(organization=organization, branch=other_branch, name="Karen Till")

        response = authenticated_client.get(TILLS_URL)

        assert response.status_code == 200
        names = [row["name"] for row in response.data["results"]]
        assert names == ["Till 1"]

    def test_duplicate_name_in_same_branch_refused(self, manager_client, branch):
        first = manager_client.post(
            TILLS_URL, {"name": "Till 1", "branch": str(branch.pk)}, format="json"
        )
        assert first.status_code == 201

        response = manager_client.post(
            TILLS_URL, {"name": "Till 1", "branch": str(branch.pk)}, format="json"
        )

        assert response.status_code == 400
        assert Till.objects.filter(name="Till 1").count() == 1

    def test_same_name_allowed_in_other_branch(self, manager_client, branch, other_branch):
        assert (
            manager_client.post(
                TILLS_URL, {"name": "Till 1", "branch": str(branch.pk)}, format="json"
            ).status_code
            == 201
        )

        response = manager_client.post(
            TILLS_URL, {"name": "Till 1", "branch": str(other_branch.pk)}, format="json"
        )

        assert response.status_code == 201

    def test_till_cannot_be_deleted_only_deactivated(self, manager_client, till):
        assert manager_client.delete(f"{TILLS_URL}{till.pk}/").status_code == 405

        response = manager_client.patch(
            f"{TILLS_URL}{till.pk}/", {"is_active": False}, format="json"
        )

        assert response.status_code == 200
        till.refresh_from_db()
        assert till.is_active is False
        assert Till.objects.filter(pk=till.pk).exists()

    def test_till_create_and_update_are_audited(self, manager_client, branch):
        created = manager_client.post(
            TILLS_URL, {"name": "Till 1", "branch": str(branch.pk)}, format="json"
        )
        assert created.status_code == 201, created.data
        manager_client.patch(
            f"{TILLS_URL}{created.data['id']}/", {"name": "Till One"}, format="json"
        )

        created_row = AuditLog.objects.get(action="till.created")
        assert created_row.entity_id == str(created.data["id"])
        assert AuditLog.objects.filter(action="till.updated").count() == 1
