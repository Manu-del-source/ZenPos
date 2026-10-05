"""Supplier directory: CRUD, scoping, permissions and audit.

The slice follows the suite's established shape: real tenants, real role
grants through the seeded system roles, and a rival organization whose rows
must never be visible or writable.
"""


import pytest

from modules.accounts.models import Role, User, UserRole
from modules.core.models import AuditLog
from modules.purchasing.models import Supplier

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures — the shared conftest has no purchasing user yet.
# ---------------------------------------------------------------------------


@pytest.fixture
def inventory_manager(make_user, branch):
    """An INVENTORY_MANAGER posted to one branch."""
    user = make_user("inventory1", role="INVENTORY_MANAGER")
    from modules.accounts.models import UserBranchAccess

    UserBranchAccess.objects.create(user=user, branch=branch, is_default=True)
    return user


@pytest.fixture
def inventory_client(api_client, inventory_manager):
    api_client.force_authenticate(user=inventory_manager)
    return api_client


@pytest.fixture
def supplier(db, organization):
    return Supplier.objects.create(
        organization=organization,
        name="Kena Distributors",
        contact_name="Alice Kena",
        phone="0733000111",
        email="sales@kenadist.co.ke",
        payment_terms="Net 30",
    )


@pytest.fixture
def other_supplier(db, other_organization):
    """A rival tenant's supplier: must never leak into any response."""
    return Supplier.objects.create(
        organization=other_organization,
        name="Rival Wholesalers",
        phone="0799000222",
    )


@pytest.fixture
def supplier_payload():
    return {
        "name": "Nairobi Foods Ltd",
        "contact_name": "Peter Mwangi",
        "phone": "0722000333",
        "email": "orders@nairobifoods.co.ke",
        "address": "Industrial Area, Nairobi",
        "payment_terms": "Net 15",
        "status": "ACTIVE",
        "notes": "Delivers Tuesdays",
    }


# ---------------------------------------------------------------------------
# List / retrieve
# ---------------------------------------------------------------------------


class TestSupplierList:
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/v2/suppliers/")
        assert response.status_code == 401

    def test_lists_own_organization_suppliers(self, inventory_client, supplier):
        response = inventory_client.get("/api/v2/suppliers/")
        assert response.status_code == 200
        names = [row["name"] for row in response.data["results"]]
        assert "Kena Distributors" in names

    def test_excludes_other_organizations(self, inventory_client, supplier, other_supplier):
        response = inventory_client.get("/api/v2/suppliers/")
        names = [row["name"] for row in response.data["results"]]
        assert "Rival Wholesalers" not in names

    def test_search_matches_name_contact_and_phone(
        self, inventory_client, supplier
    ):
        for term in ("Kena", "Alice", "0733"):
            response = inventory_client.get("/api/v2/suppliers/", {"search": term})
            names = [row["name"] for row in response.data["results"]]
            assert "Kena Distributors" in names, term

    def test_status_filter(self, inventory_client, supplier, organization):
        Supplier.objects.create(
            organization=organization, name="Blocked Wholesaler", status="BLOCKED"
        )
        response = inventory_client.get("/api/v2/suppliers/", {"status": "BLOCKED"})
        names = [row["name"] for row in response.data["results"]]
        assert names == ["Blocked Wholesaler"]

    def test_archived_suppliers_are_hidden(self, inventory_client, supplier):
        supplier.soft_delete()
        response = inventory_client.get("/api/v2/suppliers/")
        names = [row["name"] for row in response.data["results"]]
        assert "Kena Distributors" not in names

    def test_cashier_without_purchases_view_is_rejected(
        self, api_client, cashier
    ):
        api_client.force_authenticate(user=cashier)
        response = api_client.get("/api/v2/suppliers/")
        assert response.status_code == 403

    def test_user_without_organization_or_role_is_rejected(self, api_client, db):
        """Fail closed: no tenant and no role means no access at all."""
        outsider = User.objects.create_user(
            username="no-org", password="test-password-1"
        )
        assert outsider.organization_id is None
        api_client.force_authenticate(user=outsider)
        response = api_client.get("/api/v2/suppliers/")
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestSupplierCreate:
    def test_create_stamps_callers_organization(
        self, inventory_client, supplier_payload, organization
    ):
        response = inventory_client.post(
            "/api/v2/suppliers/", supplier_payload, format="json"
        )
        assert response.status_code == 201
        supplier = Supplier.objects.get(pk=response.data["id"])
        assert supplier.organization_id == organization.pk
        assert supplier.status == "ACTIVE"

    def test_create_requires_permission(self, api_client, cashier, supplier_payload):
        api_client.force_authenticate(user=cashier)
        response = api_client.post("/api/v2/suppliers/", supplier_payload, format="json")
        assert response.status_code == 403
        assert Supplier.objects.filter(name=supplier_payload["name"]).exists() is False

    def test_rejects_blank_name(self, inventory_client, supplier_payload):
        supplier_payload["name"] = "   "
        response = inventory_client.post(
            "/api/v2/suppliers/", supplier_payload, format="json"
        )
        assert response.status_code == 400
        assert response.data["name"]

    def test_rejects_duplicate_name_case_insensitive(
        self, inventory_client, supplier, supplier_payload
    ):
        supplier_payload["name"] = "kena distributors"
        response = inventory_client.post(
            "/api/v2/suppliers/", supplier_payload, format="json"
        )
        assert response.status_code == 400
        assert response.data["name"]

    def test_rejects_invalid_status(self, inventory_client, supplier_payload):
        supplier_payload["status"] = "SUSPENDED"
        response = inventory_client.post(
            "/api/v2/suppliers/", supplier_payload, format="json"
        )
        assert response.status_code == 400

    def test_rejects_client_supplied_organization(
        self, inventory_client, supplier_payload, other_organization
    ):
        """The tenant is stamped from the caller, never read from the body."""
        supplier_payload["organization"] = str(other_organization.pk)
        response = inventory_client.post(
            "/api/v2/suppliers/", supplier_payload, format="json"
        )
        assert response.status_code == 201
        assert Supplier.objects.get(pk=response.data["id"]).organization_id != (
            other_organization.pk
        )

    def test_create_is_audited(self, inventory_client, supplier_payload, inventory_manager):
        response = inventory_client.post(
            "/api/v2/suppliers/", supplier_payload, format="json"
        )
        assert AuditLog.objects.filter(
            action="supplier.created",
            entity_type="supplier",
            entity_id=response.data["id"],
            actor=inventory_manager,
        ).exists()


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class TestSupplierUpdate:
    def test_partial_update_changes_fields(self, inventory_client, supplier):
        response = inventory_client.patch(
            f"/api/v2/suppliers/{supplier.pk}/",
            {"phone": "0733444555"},
            format="json",
        )
        assert response.status_code == 200
        supplier.refresh_from_db()
        assert supplier.phone == "0733444555"

    def test_update_is_audited_with_before_and_after(
        self, inventory_client, supplier, inventory_manager
    ):
        inventory_client.patch(
            f"/api/v2/suppliers/{supplier.pk}/", {"phone": "0733444555"}, format="json"
        )
        row = AuditLog.objects.get(
            action="supplier.updated", entity_id=str(supplier.pk)
        )
        assert row.before["phone"] == "0733000111"
        assert row.after["phone"] == "0733444555"
        assert row.actor_id == inventory_manager.pk

    def test_blocking_is_audited_as_blocked(self, inventory_client, supplier):
        response = inventory_client.patch(
            f"/api/v2/suppliers/{supplier.pk}/",
            {"status": "BLOCKED"},
            format="json",
        )
        assert response.status_code == 200
        assert AuditLog.objects.filter(
            action="supplier.blocked", entity_id=str(supplier.pk)
        ).exists()

    def test_cannot_edit_another_organizations_supplier(
        self, api_client, supplier, other_organization
    ):
        """A rival tenant's staff cannot touch this organization's supplier.

        The rival belongs to ``other_organization``; the target belongs to the
        caller's own. The tenant boundary answers 404, never a 403 that
        confirms existence.
        """
        rival = User.objects.create_user(
            username="rival-staff",
            password="test-password-1",
            organization=other_organization,
        )
        role = Role.objects.get(name="INVENTORY_MANAGER", organization__isnull=True)
        UserRole.objects.create(user=rival, role=role)
        api_client.force_authenticate(user=rival)

        response = api_client.patch(
            f"/api/v2/suppliers/{supplier.pk}/",
            {"phone": "0711000999"},
            format="json",
        )
        assert response.status_code == 404
        supplier.refresh_from_db()
        assert supplier.phone == "0733000111"

    def test_rename_to_existing_live_name_is_rejected(
        self, inventory_client, supplier, organization
    ):
        Supplier.objects.create(organization=organization, name="Tusk Wholesalers")
        response = inventory_client.patch(
            f"/api/v2/suppliers/{supplier.pk}/",
            {"name": "Tusk Wholesalers"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["name"]


# ---------------------------------------------------------------------------
# Archive (delete)
# ---------------------------------------------------------------------------


class TestSupplierArchive:
    def test_destroy_archives_instead_of_deleting(self, inventory_client, supplier):
        response = inventory_client.delete(f"/api/v2/suppliers/{supplier.pk}/")
        assert response.status_code == 200
        assert Supplier.all_objects.filter(pk=supplier.pk).exists() is True
        assert Supplier.objects.filter(pk=supplier.pk).exists() is False

    def test_archive_is_audited(self, inventory_client, supplier):
        inventory_client.delete(f"/api/v2/suppliers/{supplier.pk}/")
        assert AuditLog.objects.filter(
            action="supplier.archived", entity_id=str(supplier.pk)
        ).exists()

    def test_archived_supplier_answers_404_afterwards(
        self, inventory_client, supplier
    ):
        """Like every soft-deleted row here, an archived supplier is gone."""
        first = inventory_client.delete(f"/api/v2/suppliers/{supplier.pk}/")
        second = inventory_client.delete(f"/api/v2/suppliers/{supplier.pk}/")
        assert first.status_code == 200
        assert second.status_code == 404
        assert (
            AuditLog.objects.filter(
                action="supplier.archived", entity_id=str(supplier.pk)
            ).count()
            == 1
        )

    def test_archived_name_can_be_reused(self, inventory_client, supplier):
        inventory_client.delete(f"/api/v2/suppliers/{supplier.pk}/")
        response = inventory_client.post(
            "/api/v2/suppliers/",
            {"name": "Kena Distributors", "phone": "0711222333"},
            format="json",
        )
        assert response.status_code == 201

    def test_destroy_requires_permission(self, api_client, cashier, supplier):
        api_client.force_authenticate(user=cashier)
        response = api_client.delete(f"/api/v2/suppliers/{supplier.pk}/")
        assert response.status_code == 403
        supplier.refresh_from_db()
        assert supplier.deleted_at is None
