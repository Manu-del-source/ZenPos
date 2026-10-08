"""Inter-branch transfers: dispatch, partial receive, over-receive, isolation."""

from decimal import Decimal

import pytest

from modules.core.models import AuditLog
from modules.inventory.models import InventoryMovement, StockTransfer
from modules.inventory.services import apply_stock_movement

pytestmark = pytest.mark.django_db

TRANSFERS_URL = "/api/v2/transfers/"


@pytest.fixture
def inventory_manager(make_user, branch):
    from modules.accounts.models import UserBranchAccess

    user = make_user("inv-xfer", role="INVENTORY_MANAGER")
    UserBranchAccess.objects.create(user=user, branch=branch, is_default=True)
    return user


@pytest.fixture
def xfer_client(api_client, inventory_manager):
    api_client.force_authenticate(user=inventory_manager)
    return api_client


@pytest.fixture
def product(db, organization):
    from modules.catalog.models import Product

    return Product.objects.create(
        organization=organization,
        name="Rice 5kg",
        sku="RICE-5",
        price="800.00",
        cost_price="600.00",
        stock_level=0,
    )


def _seed_source(product, branch, organization, qty=10):
    apply_stock_movement(
        product=product,
        quantity=qty,
        movement_type=InventoryMovement.MovementType.PURCHASE_RECEIPT,
        organization=organization,
        branch=branch,
        notes="seed",
    )


def _payload(source_id, dest_id, product_id, qty="10"):
    return {
        "source_branch": source_id,
        "destination_branch": dest_id,
        "notes": "Restock Karen",
        "lines": [{"product": product_id, "requested_quantity": qty}],
    }


def _advance_to_approved(client, transfer_id):
    assert client.post(f"{TRANSFERS_URL}{transfer_id}/request/").status_code == 200
    assert client.post(f"{TRANSFERS_URL}{transfer_id}/approve/").status_code == 200


class TestStockTransferLifecycle:
    def test_requires_authentication(self, api_client):
        assert api_client.get(TRANSFERS_URL).status_code == 401

    def test_cashier_cannot_create(self, api_client, cashier, branch, other_branch, product):
        api_client.force_authenticate(user=cashier)
        response = api_client.post(
            TRANSFERS_URL,
            _payload(branch.pk, other_branch.pk, product.pk),
            format="json",
        )
        assert response.status_code == 403

    def test_rejects_same_branch(self, xfer_client, branch, product):
        response = xfer_client.post(
            TRANSFERS_URL,
            _payload(branch.pk, branch.pk, product.pk),
            format="json",
        )
        assert response.status_code == 400

    def test_dispatch_decrements_source(
        self, xfer_client, branch, other_branch, product, organization
    ):
        _seed_source(product, branch, organization, 10)
        created = xfer_client.post(
            TRANSFERS_URL,
            _payload(branch.pk, other_branch.pk, product.pk, "4"),
            format="json",
        )
        assert created.status_code == 201, created.data
        tid = created.data["id"]
        _advance_to_approved(xfer_client, tid)

        dispatched = xfer_client.post(f"{TRANSFERS_URL}{tid}/dispatch/")
        assert dispatched.status_code == 200, dispatched.data
        assert dispatched.data["status"] == StockTransfer.Status.DISPATCHED

        from modules.inventory.models import BranchStock

        source = BranchStock.objects.get(branch=branch, product=product)
        dest = BranchStock.objects.filter(branch=other_branch, product=product).first()
        assert source.quantity == Decimal("6.000")
        assert dest is None or dest.quantity == 0
        assert InventoryMovement.objects.filter(
            movement_type=InventoryMovement.MovementType.TRANSFER_OUT,
            reference_id=str(tid),
        ).exists()
        assert AuditLog.objects.filter(action="transfer.dispatched", entity_id=str(tid)).exists()

        # Duplicate dispatch refused.
        again = xfer_client.post(f"{TRANSFERS_URL}{tid}/dispatch/")
        assert again.status_code == 400
        source.refresh_from_db()
        assert source.quantity == Decimal("6.000")

    def test_partial_receive_then_complete(
        self, xfer_client, branch, other_branch, product, organization
    ):
        _seed_source(product, branch, organization, 10)
        created = xfer_client.post(
            TRANSFERS_URL,
            _payload(branch.pk, other_branch.pk, product.pk, "6"),
            format="json",
        )
        tid = created.data["id"]
        line_id = created.data["lines"][0]["id"]
        _advance_to_approved(xfer_client, tid)
        assert xfer_client.post(f"{TRANSFERS_URL}{tid}/dispatch/").status_code == 200

        partial = xfer_client.post(
            f"{TRANSFERS_URL}{tid}/receive/",
            {"quantities": {line_id: "2"}},
            format="json",
        )
        assert partial.status_code == 200, partial.data
        assert partial.data["status"] == StockTransfer.Status.IN_TRANSIT
        assert Decimal(partial.data["lines"][0]["received_quantity"]) == Decimal("2")

        from modules.inventory.models import BranchStock

        dest = BranchStock.objects.get(branch=other_branch, product=product)
        assert dest.quantity == Decimal("2.000")

        rest = xfer_client.post(
            f"{TRANSFERS_URL}{tid}/receive/",
            {"quantities": {line_id: "4"}},
            format="json",
        )
        assert rest.status_code == 200, rest.data
        assert rest.data["status"] == StockTransfer.Status.RECEIVED
        dest.refresh_from_db()
        assert dest.quantity == Decimal("6.000")

    def test_over_receive_rejected(
        self, xfer_client, branch, other_branch, product, organization
    ):
        _seed_source(product, branch, organization, 10)
        created = xfer_client.post(
            TRANSFERS_URL,
            _payload(branch.pk, other_branch.pk, product.pk, "3"),
            format="json",
        )
        tid = created.data["id"]
        line_id = created.data["lines"][0]["id"]
        _advance_to_approved(xfer_client, tid)
        xfer_client.post(f"{TRANSFERS_URL}{tid}/dispatch/")
        response = xfer_client.post(
            f"{TRANSFERS_URL}{tid}/receive/",
            {"quantities": {line_id: "4"}},
            format="json",
        )
        assert response.status_code == 400
        from modules.inventory.models import BranchStock

        assert not BranchStock.objects.filter(branch=other_branch, product=product).exists()

    def test_dispatch_without_source_stock_rejected(
        self, xfer_client, branch, other_branch, product, organization
    ):
        created = xfer_client.post(
            TRANSFERS_URL,
            _payload(branch.pk, other_branch.pk, product.pk, "5"),
            format="json",
        )
        tid = created.data["id"]
        _advance_to_approved(xfer_client, tid)
        response = xfer_client.post(f"{TRANSFERS_URL}{tid}/dispatch/")
        assert response.status_code == 400
        transfer = StockTransfer.objects.get(pk=tid)
        assert transfer.status == StockTransfer.Status.APPROVED

    def test_rival_cannot_see_transfer(
        self, xfer_client, branch, other_branch, product, rival_user
    ):
        created = xfer_client.post(
            TRANSFERS_URL,
            _payload(branch.pk, other_branch.pk, product.pk, "1"),
            format="json",
        )
        assert created.status_code == 201, created.data
        from rest_framework.test import APIClient

        rival = APIClient()
        rival.force_authenticate(user=rival_user)
        response = rival.get(TRANSFERS_URL)
        assert response.data["results"] == []
        assert rival.get(f"{TRANSFERS_URL}{created.data['id']}/").status_code == 404
