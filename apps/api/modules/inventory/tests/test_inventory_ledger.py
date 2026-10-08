"""Inventory movements are append-only and match the stock they describe."""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from modules.inventory.models import InventoryMovement, StockAdjustment
from modules.inventory.services import apply_stock_movement

pytestmark = pytest.mark.django_db

MOVEMENTS_URL = "/api/v2/inventory-movements/"
ADJUSTMENTS_URL = "/api/v2/adjustments/"


class TestLedgerIsAppendOnly:
    def test_list_requires_inventory_view(self, api_client, cashier):
        api_client.force_authenticate(user=cashier)
        # Cashiers hold inventory.view.
        assert api_client.get(MOVEMENTS_URL).status_code == 200

    def test_create_is_not_allowed(self, supervisor_client):
        assert supervisor_client.post(MOVEMENTS_URL, {}, format="json").status_code == 405

    def test_adjustment_writes_a_movement(self, supervisor_client, product, supervisor):
        response = supervisor_client.post(
            ADJUSTMENTS_URL,
            {
                "product": product.id,
                "quantity": 25,
                "type": "RESTOCK",
                "notes": "Delivery",
            },
            format="json",
        )
        assert response.status_code == 201, response.data
        product.refresh_from_db()
        assert product.stock_level == 75
        movement = InventoryMovement.objects.get()
        assert movement.movement_type == InventoryMovement.MovementType.PURCHASE_RECEIPT
        assert movement.quantity == Decimal("25")
        assert movement.quantity_after - movement.quantity_before == movement.quantity
        assert StockAdjustment.objects.get().quantity == 25

    def test_anonymous_list_rejected(self, api_client):
        assert api_client.get(MOVEMENTS_URL).status_code in (401, 403)

    def test_rival_cannot_read_movements(
        self, supervisor_client, product, rival_client
    ):
        supervisor_client.post(
            ADJUSTMENTS_URL,
            {"product": product.id, "quantity": 1, "type": "ADJUST", "notes": "x"},
            format="json",
        )
        response = rival_client.get(MOVEMENTS_URL)
        assert response.status_code == 200
        assert response.data["results"] == []


class TestApplyMovement:
    def test_rejects_zero_quantity(self, product, branch, organization):
        from rest_framework.exceptions import ValidationError

        with pytest.raises(ValidationError):
            apply_stock_movement(
                product=product,
                quantity=0,
                movement_type=InventoryMovement.MovementType.ADJUSTMENT,
                organization=organization,
                branch=branch,
            )

    def test_rejects_oversell_at_branch(self, product, branch, organization):
        from rest_framework.exceptions import ValidationError

        product.stock_level = 0
        product.save(update_fields=["stock_level"])
        apply_stock_movement(
            product=product,
            quantity=2,
            movement_type=InventoryMovement.MovementType.PURCHASE_RECEIPT,
            organization=organization,
            branch=branch,
        )
        with pytest.raises(ValidationError):
            apply_stock_movement(
                product=product,
                quantity=-3,
                movement_type=InventoryMovement.MovementType.SALE,
                organization=organization,
                branch=branch,
            )
