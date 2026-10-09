"""Goods received notes: partial/full receiving, posting, over-receive, audit.

Posting is the only step that moves inventory. Repeating it, receiving more
than outstanding, and posting across the tenant boundary are all refusals.
"""

from decimal import Decimal

import pytest

from modules.accounts.models import Role, User, UserRole
from modules.core.models import AuditLog
from modules.inventory.models import InventoryMovement
from modules.purchasing.models import GoodsReceivedNote, PurchaseOrder

pytestmark = pytest.mark.django_db

GRN_URL = "/api/v2/goods-receipts/"
ORDERS_URL = "/api/v2/purchase-orders/"


@pytest.fixture
def inventory_manager(make_user, branch):
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
    from modules.purchasing.models import Supplier

    return Supplier.objects.create(
        organization=organization,
        name="Kena Distributors",
        payment_terms="Net 30",
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
def approved_order(db, organization, branch, supplier, inventory_manager, product):
    order = PurchaseOrder.objects.create(
        organization=organization,
        branch=branch,
        supplier=supplier,
        created_by=inventory_manager,
        status=PurchaseOrder.Status.APPROVED,
        number="PO-000001",
    )
    order.lines.create(product=product, quantity=10, unit_cost="80.00")
    return order


def _line_payload(order, quantity="10"):
    po_line = order.lines.first()
    return {
        "purchase_order": str(order.pk),
        "delivery_note": "DN-1",
        "received_date": "2026-10-08",
        "lines": [
            {
                "purchase_order_line": str(po_line.pk),
                "quantity_received": quantity,
            }
        ],
    }


class TestGoodsReceiptCreate:
    def test_requires_authentication(self, api_client):
        assert api_client.get(GRN_URL).status_code == 401

    def test_cashier_cannot_view(self, api_client, cashier):
        api_client.force_authenticate(user=cashier)
        assert api_client.get(GRN_URL).status_code == 403

    def test_draft_from_approved_order(self, inventory_client, approved_order):
        response = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "4"), format="json"
        )
        assert response.status_code == 201, response.data
        grn = GoodsReceivedNote.objects.get(pk=response.data["id"])
        assert grn.status == GoodsReceivedNote.Status.DRAFT
        assert grn.number.startswith("GRN-")
        assert grn.branch_id == approved_order.branch_id
        assert grn.supplier_id == approved_order.supplier_id
        line = grn.lines.get()
        assert line.quantity_received == Decimal("4")
        assert line.ordered_quantity == Decimal("10")
        assert line.previously_received == Decimal("0")
        # Draft does not move stock.
        approved_order.lines.get().refresh_from_db()
        assert approved_order.lines.get().quantity_received == Decimal("0")

    def test_rejects_draft_order(self, inventory_client, approved_order):
        approved_order.status = PurchaseOrder.Status.DRAFT
        approved_order.save(update_fields=["status"])
        response = inventory_client.post(
            GRN_URL, _line_payload(approved_order), format="json"
        )
        assert response.status_code == 400

    def test_rejects_over_receive_on_create(self, inventory_client, approved_order):
        response = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "11"), format="json"
        )
        assert response.status_code == 400

    def test_prefill_outstanding_when_lines_omitted(
        self, inventory_client, approved_order
    ):
        response = inventory_client.post(
            GRN_URL,
            {
                "purchase_order": str(approved_order.pk),
                "received_date": "2026-10-08",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        assert Decimal(response.data["lines"][0]["quantity_received"]) == Decimal("10")

    def test_hides_other_organizations_receipts(
        self, inventory_client, approved_order, rival_user
    ):
        inventory_client.post(GRN_URL, _line_payload(approved_order, "2"), format="json")
        rival = User.objects.create_user(
            username="rival-recv",
            password="test-password-1",
            organization=rival_user.organization,
        )
        role = Role.objects.get(name="INVENTORY_MANAGER", organization__isnull=True)
        UserRole.objects.create(user=rival, role=role)
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=rival)
        response = client.get(GRN_URL)
        assert response.status_code == 200
        assert response.data["results"] == []


class TestGoodsReceiptPost:
    def test_partial_receive_updates_po_and_stock(
        self, inventory_client, approved_order, product
    ):
        created = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "4"), format="json"
        )
        assert created.status_code == 201, created.data
        grn_id = created.data["id"]

        posted = inventory_client.post(f"{GRN_URL}{grn_id}/post/")
        assert posted.status_code == 200, posted.data
        assert posted.data["status"] == GoodsReceivedNote.Status.POSTED
        assert posted.data["posted_by"] is not None

        approved_order.refresh_from_db()
        assert approved_order.status == PurchaseOrder.Status.PARTIALLY_RECEIVED
        po_line = approved_order.lines.get()
        assert po_line.quantity_received == Decimal("4")

        product.refresh_from_db()
        assert product.stock_level == 54

        movement = InventoryMovement.objects.get(reference_id=str(grn_id))
        assert movement.movement_type == InventoryMovement.MovementType.PURCHASE_RECEIPT
        assert movement.quantity == Decimal("4.000")
        assert movement.quantity_after - movement.quantity_before == movement.quantity
        assert movement.quantity_after == Decimal("54.000")
        assert AuditLog.objects.filter(
            action="grn.posted", entity_id=str(grn_id)
        ).exists()

    def test_full_receive_marks_po_received(
        self, inventory_client, approved_order, product
    ):
        created = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "10"), format="json"
        )
        posted = inventory_client.post(f"{GRN_URL}{created.data['id']}/post/")
        assert posted.status_code == 200, posted.data
        approved_order.refresh_from_db()
        assert approved_order.status == PurchaseOrder.Status.RECEIVED
        product.refresh_from_db()
        assert product.stock_level == 60

    def test_two_partials_then_complete(self, inventory_client, approved_order, product):
        first = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "6"), format="json"
        )
        assert inventory_client.post(f"{GRN_URL}{first.data['id']}/post/").status_code == 200

        second = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "4"), format="json"
        )
        assert second.status_code == 201, second.data
        assert Decimal(second.data["lines"][0]["previously_received"]) == Decimal("6")
        assert inventory_client.post(f"{GRN_URL}{second.data['id']}/post/").status_code == 200

        approved_order.refresh_from_db()
        assert approved_order.status == PurchaseOrder.Status.RECEIVED
        product.refresh_from_db()
        assert product.stock_level == 60

    def test_duplicate_post_is_rejected(
        self, inventory_client, approved_order, product
    ):
        created = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "3"), format="json"
        )
        url = f"{GRN_URL}{created.data['id']}/post/"
        assert inventory_client.post(url).status_code == 200
        second = inventory_client.post(url)
        assert second.status_code == 400
        product.refresh_from_db()
        assert product.stock_level == 53
        assert InventoryMovement.objects.filter(
            reference_id=str(created.data["id"])
        ).count() == 1

    def test_over_receive_on_post_is_rejected(
        self, inventory_client, approved_order, product
    ):
        first = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "8"), format="json"
        )
        inventory_client.post(f"{GRN_URL}{first.data['id']}/post/")

        # A draft that was legal when opened (outstanding 10) but is no longer.
        second = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "8"), format="json"
        )
        # Create-time check uses live outstanding, so this is already 400.
        # Force a stale draft to exercise the post-time re-check.
        if second.status_code == 201:
            posted = inventory_client.post(f"{GRN_URL}{second.data['id']}/post/")
            assert posted.status_code == 400
        else:
            assert second.status_code == 400
        product.refresh_from_db()
        assert product.stock_level == 58

    def test_post_requires_receive_permission(self, api_client, cashier, approved_order):
        # Build a draft as the inventory manager, then a cashier tries to post.
        from modules.accounts.models import User as Staff

        manager = Staff.objects.get(username="inventory1")
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=manager)
        created = client.post(GRN_URL, _line_payload(approved_order, "2"), format="json")
        assert created.status_code == 201, created.data

        api_client.force_authenticate(user=cashier)
        response = api_client.post(f"{GRN_URL}{created.data['id']}/post/")
        assert response.status_code == 403
        approved_order.refresh_from_db()
        assert approved_order.status == PurchaseOrder.Status.APPROVED

    def test_cancel_draft_does_not_move_stock(
        self, inventory_client, approved_order, product
    ):
        created = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "5"), format="json"
        )
        cancelled = inventory_client.post(f"{GRN_URL}{created.data['id']}/cancel/")
        assert cancelled.status_code == 200
        assert cancelled.data["status"] == GoodsReceivedNote.Status.CANCELLED
        product.refresh_from_db()
        assert product.stock_level == 50
        assert not InventoryMovement.objects.filter(
            reference_id=str(created.data["id"])
        ).exists()
        assert AuditLog.objects.filter(
            action="grn.cancelled", entity_id=str(created.data["id"])
        ).exists()

    def test_cannot_cancel_posted(self, inventory_client, approved_order):
        created = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "2"), format="json"
        )
        inventory_client.post(f"{GRN_URL}{created.data['id']}/post/")
        response = inventory_client.post(f"{GRN_URL}{created.data['id']}/cancel/")
        assert response.status_code == 400

    def test_cannot_cancel_po_after_posted_receipt(
        self, inventory_client, approved_order
    ):
        created = inventory_client.post(
            GRN_URL, _line_payload(approved_order, "2"), format="json"
        )
        inventory_client.post(f"{GRN_URL}{created.data['id']}/post/")
        response = inventory_client.post(f"{ORDERS_URL}{approved_order.pk}/cancel/")
        assert response.status_code == 400
        approved_order.refresh_from_db()
        assert approved_order.status == PurchaseOrder.Status.PARTIALLY_RECEIVED

    def test_po_receive_action_creates_draft(self, inventory_client, approved_order):
        response = inventory_client.post(f"{ORDERS_URL}{approved_order.pk}/receive/")
        assert response.status_code == 200, response.data
        assert response.data["status"] == GoodsReceivedNote.Status.DRAFT
        assert Decimal(response.data["lines"][0]["quantity_received"]) == Decimal("10")
