"""Staff records: tenant isolation and status changes."""

import pytest

from modules.accounts.models import Employee
from modules.core.models import AuditLog

pytestmark = pytest.mark.django_db

EMP_URL = "/api/v2/employees/"


class TestEmployees:
    def test_manager_creates_employee(self, manager_client, branch):
        response = manager_client.post(
            EMP_URL,
            {
                "first_name": "Amina",
                "last_name": "Otieno",
                "phone": "0711000000",
                "branch": branch.pk,
                "start_date": "2026-01-15",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["employee_number"].startswith("EMP-")
        assert response.data["status"] == Employee.Status.ACTIVE
        assert AuditLog.objects.filter(action="staff.created").exists()

    def test_cashier_cannot_manage_staff(self, authenticated_client):
        assert authenticated_client.get(EMP_URL).status_code == 403

    def test_status_change_is_audited(self, manager_client, organization, branch):
        emp = Employee.objects.create(
            organization=organization,
            employee_number="EMP-000001",
            first_name="John",
            last_name="Mwangi",
            branch=branch,
        )
        response = manager_client.patch(
            f"{EMP_URL}{emp.pk}/",
            {"status": "SUSPENDED"},
            format="json",
        )
        assert response.status_code == 200, response.data
        emp.refresh_from_db()
        assert emp.status == Employee.Status.SUSPENDED
        assert AuditLog.objects.filter(action="staff.status_changed", entity_id=str(emp.pk)).exists()

    def test_rival_cannot_see_employees(self, manager_client, rival_client, organization):
        Employee.objects.create(
            organization=organization,
            employee_number="EMP-000002",
            first_name="Hidden",
            last_name="Staff",
        )
        response = rival_client.get(EMP_URL)
        assert response.status_code == 200
        assert response.data["results"] == []
