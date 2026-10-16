import pytest

from modules.branches.models import Branch
from modules.core.models import AuditLog

BRANCHES_URL = "/api/v2/branches/"


@pytest.mark.django_db
class TestPlatformBranchDeactivation:
    def test_platform_super_admin_can_deactivate_any_branch(
        self, platform_client, branch
    ):
        response = platform_client.delete(f"{BRANCHES_URL}{branch.id}/")

        assert response.status_code == 204
        branch.refresh_from_db()
        assert branch.is_active is False
        assert Branch.objects.filter(pk=branch.pk).exists()
        assert AuditLog.objects.filter(
            action="branch.deactivated_by_platform",
            entity_type="branch",
            entity_id=branch.pk,
        ).exists()

    def test_business_manager_cannot_use_platform_delete(
        self, manager_client, branch
    ):
        response = manager_client.delete(f"{BRANCHES_URL}{branch.id}/")

        assert response.status_code == 405
        branch.refresh_from_db()
        assert branch.is_active is True
