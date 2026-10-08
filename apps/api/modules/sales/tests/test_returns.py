"""Retail returns: quantity caps, duplicate refunds, inventory, permissions."""

from decimal import Decimal

import pytest

from modules.core.models import AuditLog
from modules.inventory.models import InventoryMovement
from modules.payments.models import Payment
from modules.sales.models import Sale, SaleReturn

pytestmark = pytest.mark.django_db

SALES_URL = "/api/v2/sales/"
RETURNS_URL = "/api/v2/returns/"


def _sell(client, product, quantity=2):
    response = client.post(
        SALES_URL,
        {
            "payment_method": "CASH",
            "items": [{"product": product.id, "quantity": quantity}],
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


class TestReturns:
    def test_cannot_return_more_than_sold(self, authenticated_client, product):
        sale = _sell(authenticated_client, product, 2)
        item_id = sale["items"][0]["id"]
        response = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {
                "reason": "WRONG_ITEM",
                "refund_method": "CASH",
                "lines": [{"sale_item": item_id, "quantity": 3}],
            },
            format="json",
        )
        assert response.status_code == 400

    def test_complete_return_restocks_and_records_refund(
        self, authenticated_client, supervisor_client, product
    ):
        sale = _sell(authenticated_client, product, 2)
        product.refresh_from_db()
        stock_after_sale = product.stock_level
        item_id = sale["items"][0]["id"]

        requested = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {
                "reason": "CUSTOMER_CHANGE",
                "refund_method": "CASH",
                "lines": [{"sale_item": item_id, "quantity": 1, "restock": True}],
            },
            format="json",
        )
        assert requested.status_code == 200, requested.data
        ret_id = requested.data["id"]
        assert requested.data["status"] == SaleReturn.Status.REQUESTED
        assert Decimal(requested.data["refund_amount"]) == Decimal("100.00")

        completed = supervisor_client.post(f"{RETURNS_URL}{ret_id}/complete/")
        assert completed.status_code == 200, completed.data
        assert completed.data["status"] == SaleReturn.Status.COMPLETED

        product.refresh_from_db()
        assert product.stock_level == stock_after_sale + 1
        assert InventoryMovement.objects.filter(
            reference_id=str(ret_id),
            movement_type=InventoryMovement.MovementType.RETURN,
        ).exists()
        assert Payment.objects.filter(
            sale_id=sale["id"], status=Payment.Status.REFUNDED
        ).exists()
        assert AuditLog.objects.filter(action="refund.completed", entity_id=str(ret_id)).exists()

        # Duplicate complete is a no-op on inventory.
        again = supervisor_client.post(f"{RETURNS_URL}{ret_id}/complete/")
        assert again.status_code == 200
        product.refresh_from_db()
        assert product.stock_level == stock_after_sale + 1

    def test_second_return_cannot_exceed_remaining(
        self, authenticated_client, supervisor_client, product
    ):
        sale = _sell(authenticated_client, product, 2)
        item_id = sale["items"][0]["id"]
        first = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {
                "reason": "OTHER",
                "lines": [{"sale_item": item_id, "quantity": 2}],
            },
            format="json",
        )
        supervisor_client.post(f"{RETURNS_URL}{first.data['id']}/complete/")

        second = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {
                "reason": "OTHER",
                "lines": [{"sale_item": item_id, "quantity": 1}],
            },
            format="json",
        )
        assert second.status_code == 400

    def test_cannot_return_voided_sale(self, authenticated_client, supervisor_client, product):
        sale = _sell(authenticated_client, product, 1)
        supervisor_client.post(f"{SALES_URL}{sale['id']}/void/", {"reason": "mistake"}, format="json")
        item_id = sale["items"][0]["id"]
        response = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {"reason": "OTHER", "lines": [{"sale_item": item_id, "quantity": 1}]},
            format="json",
        )
        assert response.status_code == 400

    def test_cashier_cannot_complete(self, authenticated_client, product):
        sale = _sell(authenticated_client, product, 1)
        item_id = sale["items"][0]["id"]
        requested = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {"reason": "OTHER", "lines": [{"sale_item": item_id, "quantity": 1}]},
            format="json",
        )
        response = authenticated_client.post(f"{RETURNS_URL}{requested.data['id']}/complete/")
        assert response.status_code == 403

    def test_rival_cannot_see_return(
        self, authenticated_client, rival_user, product
    ):
        sale = _sell(authenticated_client, product, 1)
        item_id = sale["items"][0]["id"]
        requested = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {"reason": "OTHER", "lines": [{"sale_item": item_id, "quantity": 1}]},
            format="json",
        )
        from rest_framework.test import APIClient

        rival = APIClient()
        rival.force_authenticate(user=rival_user)
        assert rival.get(RETURNS_URL).data["results"] == []
        assert rival.get(f"{RETURNS_URL}{requested.data['id']}/").status_code == 404
