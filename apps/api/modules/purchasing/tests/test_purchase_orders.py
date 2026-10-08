"""Purchase orders: the enforced lifecycle, tenant boundaries, and audit.

The slice follows the suite's established shape: real tenants, real role
grants through the seeded system roles, and a rival organization whose rows
must never be visible or writable. The state machine is exercised at every
edge — the transitions that are allowed are tested once with their audit row,
the ones that are not are tested to answer 400 without changing the order.
"""


import pytest
from django.utils import timezone

from modules.accounts.models import Role, User, UserRole
from modules.core.models import AuditLog
from modules.purchasing.models import PurchaseOrder, Supplier

pytestmark = pytest.mark.django_db

ORDERS_URL = "/api/v2/purchase-orders/"


# ---------------------------------------------------------------------------
# Fixtures — extend the shared conftest with purchasing-specific data.
# ---------------------------------------------------------------------------


@pytest.fixture
def inventory_manager(make_user, branch):
    """An INVENTORY_MANAGER posted to one branch: raises orders, cannot approve."""
    user = make_user("inventory1", role="INVENTORY_MANAGER")
    from modules.accounts.models import UserBranchAccess

    UserBranchAccess.objects.create(user=user, branch=branch, is_default=True)
    return user


@pytest.fixture
def inventory_client(api_client, inventory_manager):
    api_client.force_authenticate(user=inventory_manager)
    return api_client


@pytest.fixture
def approving_manager(make_user, branch):
    """A MANAGER with purchases.approve: the other half of the workflow."""
    user = make_user("approver1", role="MANAGER")
    from modules.accounts.models import UserBranchAccess

    UserBranchAccess.objects.create(user=user, branch=branch, is_default=True)
    return user


@pytest.fixture
def approver_client(api_client, approving_manager):
    api_client.force_authenticate(user=approving_manager)
    return api_client


@pytest.fixture
def supplier(db, organization):
    return Supplier.objects.create(
        organization=organization,
        name="Kena Distributors",
        payment_terms="Net 30",
    )


@pytest.fixture
def other_supplier(db, other_organization):
    return Supplier.objects.create(
        organization=other_organization,
        name="Rival Wholesalers",
    )


@pytest.fixture
def product(db, organization):
    from modules.catalog.models import Product

    return Product.objects.create(
        organization=organization,
        name="Milk 1L",
        sku="MILK-1L",
        price="100.00",
        cost_price="80.00",
        stock_level=50,
    )


@pytest.fixture
def foreign_product(db, other_organization):
    from modules.catalog.models import Product

    return Product.objects.create(
        organization=other_organization,
        name="Rival Milk 1L",
        sku="RIVAL-MILK-1L",
        price="90.00",
        cost_price="70.00",
        stock_level=5,
    )


@pytest.fixture
def draft_order(db, organization, branch, supplier, inventory_manager, product):
    order = PurchaseOrder.objects.create(
        organization=organization,
        branch=branch,
        supplier=supplier,
        created_by=inventory_manager,
    )
    order.lines.create(
        product=product,
        quantity=10,
        unit_cost="80.00",
    )
    return order


def draft_payload(branch_id, supplier_id, product_id, product_cost=None, **extra):
    lines = [
        {
            "product": product_id,
            "quantity": "10",
        }
    ]
    if product_cost is not None:
        lines[0]["unit_cost"] = product_cost
    payload = {
        "branch": branch_id,
        "supplier": supplier_id,
        "expected_date": str(timezone.localdate()),
        "lines": lines,
    }
    payload.update(extra)
    return payload


# ---------------------------------------------------------------------------
# List / retrieve
# ---------------------------------------------------------------------------


class TestPurchaseOrderList:
    def test_requires_authentication(self, api_client):
        assert api_client.get(ORDERS_URL).status_code == 401

    def test_lists_own_organization_orders(
        self, inventory_client, draft_order
    ):
        response = inventory_client.get(ORDERS_URL)
        assert response.status_code == 200
        numbers = [row["number"] for row in response.data["results"]]
        assert draft_order.number in numbers

    def test_excludes_other_organizations(
        self, api_client, rival_user, organization, branch, supplier, product
    ):
        """The rival builds a real order in their own tenant; ours must hide it."""
        rival_order = PurchaseOrder.objects.create(
            organization=rival_user.organization,
            branch=branch,
            supplier=supplier,
        )
        rival_order.lines.create(product=product, quantity=1, unit_cost="80.00")

        # A manager from the rival's organization reads through the same URL.
        rival = User.objects.create_user(
            username="rival-staff",
            password="test-password-1",
            organization=rival_user.organization,
        )
        role = Role.objects.get(name="INVENTORY_MANAGER", organization__isnull=True)
        UserRole.objects.create(user=rival, role=role)
        api_client.force_authenticate(user=rival)

        response = api_client.get(ORDERS_URL)
        numbers = [row["number"] for row in response.data["results"]]
        assert numbers == [rival_order.number]

    def test_cashier_without_purchases_view_is_rejected(self, api_client, cashier):
        api_client.force_authenticate(user=cashier)
        assert api_client.get(ORDERS_URL).status_code == 403

    def test_archived_orders_are_hidden(self, inventory_client, draft_order):
        draft_order.soft_delete()
        response = inventory_client.get(ORDERS_URL)
        numbers = [row["number"] for row in response.data["results"]]
        assert draft_order.number not in numbers

    def test_number_and_status_filter(self, inventory_client, draft_order):
        response = inventory_client.get(ORDERS_URL, {"status": "DRAFT"})
        numbers = [row["number"] for row in response.data["results"]]
        assert numbers == [draft_order.number]

        draft_order.status = PurchaseOrder.Status.SUBMITTED
        draft_order.save(update_fields=["status"])
        response = inventory_client.get(ORDERS_URL, {"status": "DRAFT"})
        assert response.data["results"] == []


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class TestPurchaseOrderCreate:
    def test_create_stamps_tenant_author_and_number(
        self, inventory_client, branch, supplier, product, organization
    ):
        payload = draft_payload(branch.pk, supplier.pk, product.pk)
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 201

        order = PurchaseOrder.objects.get(pk=response.data["id"])
        assert order.organization_id == organization.pk
        assert order.created_by.username == "inventory1"
        assert order.number.startswith("PO-")
        assert order.status == PurchaseOrder.Status.DRAFT
        # unit_cost defaulted from the product's cost price
        assert str(order.lines.first().unit_cost) == "80.00"

    def test_numbers_are_sequential_per_organization(
        self, inventory_client, branch, supplier, product
    ):
        first = inventory_client.post(
            ORDERS_URL,
            draft_payload(branch.pk, supplier.pk, product.pk),
            format="json",
        )
        second = inventory_client.post(
            ORDERS_URL,
            draft_payload(branch.pk, supplier.pk, product.pk),
            format="json",
        )
        assert second.data["number"] == f"PO-{int(first.data['number'][3:]) + 1:06d}"

    def test_create_requires_permission(self, api_client, cashier, branch, supplier, product):
        api_client.force_authenticate(user=cashier)
        response = api_client.post(
            ORDERS_URL,
            draft_payload(branch.pk, supplier.pk, product.pk),
            format="json",
        )
        assert response.status_code == 403

    def test_rejects_foreign_branch(
        self, inventory_client, foreign_branch, supplier, product
    ):
        payload = draft_payload(foreign_branch.pk, supplier.pk, product.pk)
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 400
        assert response.data["branch"]

    def test_rejects_foreign_supplier(
        self, inventory_client, branch, other_supplier, product
    ):
        payload = draft_payload(branch.pk, other_supplier.pk, product.pk)
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 400
        assert response.data["supplier"]

    def test_rejects_foreign_product(
        self, inventory_client, branch, supplier, foreign_product
    ):
        payload = draft_payload(branch.pk, supplier.pk, foreign_product.pk)
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 400
        assert response.data["lines"]

    def test_rejects_blocked_supplier(
        self, inventory_client, branch, supplier, product
    ):
        """A BLOCKED supplier keeps their history but takes no new orders."""
        supplier.status = Supplier.Status.BLOCKED
        supplier.save(update_fields=["status"])
        payload = draft_payload(branch.pk, supplier.pk, product.pk)
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 400

    def test_rejects_order_without_lines(
        self, inventory_client, branch, supplier, product
    ):
        payload = draft_payload(branch.pk, supplier.pk, product.pk)
        payload["lines"] = []
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 400

    def test_rejects_zero_quantity(
        self, inventory_client, branch, supplier, product
    ):
        payload = draft_payload(branch.pk, supplier.pk, product.pk)
        payload["lines"][0]["quantity"] = "0"
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 400

    def test_rejects_negative_unit_cost(
        self, inventory_client, branch, supplier, product
    ):
        payload = draft_payload(
            branch.pk, supplier.pk, product.pk, product_cost="-1.00"
        )
        response = inventory_client.post(ORDERS_URL, payload, format="json")
        assert response.status_code == 400

    def test_create_is_audited(self, inventory_client, branch, supplier, product):
        response = inventory_client.post(
            ORDERS_URL,
            draft_payload(branch.pk, supplier.pk, product.pk),
            format="json",
        )
        assert AuditLog.objects.filter(
            action="purchase_order.created",
            entity_type="purchase_order",
            entity_id=response.data["id"],
        ).exists()


# ---------------------------------------------------------------------------
# Edit (draft only)
# ---------------------------------------------------------------------------


class TestPurchaseOrderEdit:
    def test_draft_lines_can_be_replaced(self, inventory_client, draft_order, product):
        second = type(product).objects.create(
            organization=draft_order.organization,
            name="Bread 400g",
            sku="BREAD-400G",
            price="50.00",
            cost_price="30.00",
        )
        payload = {
            "lines": [
                {"product": str(second.pk), "quantity": "4", "unit_cost": "30.00"}
            ]
        }
        response = inventory_client.patch(
            f"{ORDERS_URL}{draft_order.pk}/", payload, format="json"
        )
        assert response.status_code == 200
        draft_order.refresh_from_db()
        assert draft_order.lines.count() == 1
        assert draft_order.lines.first().product_id == second.pk

    def test_submitted_order_is_not_editable(
        self, inventory_client, draft_order, product
    ):
        draft_order.status = PurchaseOrder.Status.SUBMITTED
        draft_order.save(update_fields=["status"])

        payload = {"notes": "supplier changed the price"}
        response = inventory_client.patch(
            f"{ORDERS_URL}{draft_order.pk}/", payload, format="json"
        )
        assert response.status_code == 400
        draft_order.refresh_from_db()
        assert draft_order.notes == ""

        payload = {"lines": [{"product": str(product.pk), "quantity": "99"}]}
        response = inventory_client.patch(
            f"{ORDERS_URL}{draft_order.pk}/", payload, format="json"
        )
        assert response.status_code == 400
        draft_order.refresh_from_db()
        assert draft_order.lines.first().quantity == 10

    def test_edit_is_audited(self, inventory_client, draft_order):
        inventory_client.patch(
            f"{ORDERS_URL}{draft_order.pk}/", {"notes": "rush this"}, format="json"
        )
        row = AuditLog.objects.get(
            action="purchase_order.updated",
            entity_id=str(draft_order.pk),
        )
        assert row.before["notes"] == ""
        assert row.after["notes"] == "rush this"


# ---------------------------------------------------------------------------
# Lifecycle: submit / approve / reject / cancel
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_submit_moves_draft_to_submitted(self, inventory_client, draft_order):
        response = inventory_client.post(f"{ORDERS_URL}{draft_order.pk}/submit/")
        assert response.status_code == 200
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.SUBMITTED
        assert AuditLog.objects.filter(
            action="purchase_order.submitted",
            entity_id=str(draft_order.pk),
        ).exists()

    def test_submit_twice_is_refused(self, inventory_client, draft_order):
        inventory_client.post(f"{ORDERS_URL}{draft_order.pk}/submit/")
        second = inventory_client.post(f"{ORDERS_URL}{draft_order.pk}/submit/")
        assert second.status_code == 400
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.SUBMITTED

    def test_submit_requires_permission(self, api_client, cashier, draft_order):
        api_client.force_authenticate(user=cashier)
        response = api_client.post(f"{ORDERS_URL}{draft_order.pk}/submit/")
        assert response.status_code == 403
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.DRAFT

    def test_approve_moves_submitted_to_approved(self, approver_client, draft_order):
        # The draft must be submitted before approval will accept it.
        draft_order.status = PurchaseOrder.Status.SUBMITTED
        draft_order.save(update_fields=["status"])

        response = approver_client.post(f"{ORDERS_URL}{draft_order.pk}/approve/")
        assert response.status_code == 200
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.APPROVED
        assert draft_order.approved_by_id is not None
        assert draft_order.approved_at is not None
        assert AuditLog.objects.filter(
            action="purchase_order.approved",
            entity_id=str(draft_order.pk),
        ).exists()

    def test_approve_requires_permission(self, inventory_client, draft_order):
        """The raiser's INVENTORY_MANAGER grant does not include approval."""
        draft_order.status = PurchaseOrder.Status.SUBMITTED
        draft_order.save(update_fields=["status"])
        response = inventory_client.post(f"{ORDERS_URL}{draft_order.pk}/approve/")
        assert response.status_code == 403
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.SUBMITTED

    def test_approve_of_draft_is_refused(self, approver_client, draft_order):
        """The state machine skips nothing: a draft must be submitted first."""
        response = approver_client.post(f"{ORDERS_URL}{draft_order.pk}/approve/")
        assert response.status_code == 400
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.DRAFT

    def test_reject_returns_order_to_draft_with_note(
        self, approver_client, draft_order
    ):
        draft_order.status = PurchaseOrder.Status.SUBMITTED
        draft_order.save(update_fields=["status"])

        response = approver_client.post(
            f"{ORDERS_URL}{draft_order.pk}/reject/",
            {"notes": "price is above the agreed contract"},
            format="json",
        )
        assert response.status_code == 200
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.DRAFT
        assert draft_order.notes == "price is above the agreed contract"
        assert AuditLog.objects.filter(
            action="purchase_order.rejected",
            entity_id=str(draft_order.pk),
        ).exists()

    def test_reject_requires_a_note(self, approver_client, draft_order):
        draft_order.status = PurchaseOrder.Status.SUBMITTED
        draft_order.save(update_fields=["status"])
        response = approver_client.post(
            f"{ORDERS_URL}{draft_order.pk}/reject/", {}, format="json"
        )
        assert response.status_code == 400
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.SUBMITTED

    def test_cancel_from_open_state(self, approver_client, draft_order):
        """Cancel works from any open state, including DRAFT."""
        response = approver_client.post(f"{ORDERS_URL}{draft_order.pk}/cancel/")
        assert response.status_code == 200
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.CANCELLED
        assert AuditLog.objects.filter(
            action="purchase_order.cancelled",
            entity_id=str(draft_order.pk),
        ).exists()

    def test_cancelled_is_terminal(self, approver_client, draft_order):
        """A cancelled order cannot be submitted, nor cancelled twice."""
        draft_order.status = PurchaseOrder.Status.CANCELLED
        draft_order.save(update_fields=["status"])

        for action in ("submit", "cancel"):
            response = approver_client.post(f"{ORDERS_URL}{draft_order.pk}/{action}/")
            assert response.status_code == 400, action
        draft_order.refresh_from_db()
        assert draft_order.status == PurchaseOrder.Status.CANCELLED

    def test_received_is_terminal_to_any_change(self, approver_client, draft_order):
        """RECEIVED has no outgoing transitions; nothing un-receives an order."""
        draft_order.status = PurchaseOrder.Status.RECEIVED
        draft_order.save(update_fields=["status"])
        for action in ("submit", "cancel"):
            response = approver_client.post(f"{ORDERS_URL}{draft_order.pk}/{action}/")
            assert response.status_code == 400, action


# ---------------------------------------------------------------------------
# Delete (archive a draft only)
# ---------------------------------------------------------------------------


class TestPurchaseOrderDelete:
    def test_draft_can_be_archived(self, inventory_client, draft_order):
        response = inventory_client.delete(f"{ORDERS_URL}{draft_order.pk}/")
        assert response.status_code == 200
        assert PurchaseOrder.objects.filter(pk=draft_order.pk).exists() is False
        assert PurchaseOrder.all_objects.filter(pk=draft_order.pk).exists() is True
        assert AuditLog.objects.filter(
            action="purchase_order.archived",
            entity_id=str(draft_order.pk),
        ).exists()

    def test_submitted_order_cannot_be_archived(self, inventory_client, draft_order):
        """A submitted order has history; it is cancelled, not deleted."""
        draft_order.status = PurchaseOrder.Status.SUBMITTED
        draft_order.save(update_fields=["status"])
        response = inventory_client.delete(f"{ORDERS_URL}{draft_order.pk}/")
        assert response.status_code == 400
        assert PurchaseOrder.objects.filter(pk=draft_order.pk).exists() is True

    def test_delete_requires_permission(self, api_client, cashier, draft_order):
        api_client.force_authenticate(user=cashier)
        response = api_client.delete(f"{ORDERS_URL}{draft_order.pk}/")
        assert response.status_code == 403
        assert PurchaseOrder.objects.filter(pk=draft_order.pk).exists() is True

    def test_cannot_delete_another_organizations_order(
        self, api_client, draft_order
    ):
        rival = User.objects.create_user(
            username="rival-po",
            password="test-password-1",
            organization=draft_order.organization,  # replaced below
        )
        # Belong to the rival tenant instead.
        from modules.organizations.models import Organization

        rival_org = Organization.objects.create(name="Second Rival", slug="second-rival")
        rival.organization = rival_org
        rival.save(update_fields=["organization"])

        role = Role.objects.get(name="INVENTORY_MANAGER", organization__isnull=True)
        UserRole.objects.create(user=rival, role=role)
        api_client.force_authenticate(user=rival)

        response = api_client.delete(f"{ORDERS_URL}{draft_order.pk}/")
        assert response.status_code == 404
        assert PurchaseOrder.objects.filter(pk=draft_order.pk).exists() is True
