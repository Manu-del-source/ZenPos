"""Loyalty ledger: earn once, reverse on return, no negative balance."""

import pytest

from modules.loyalty.models import LoyaltyLedger, LoyaltyRule
from modules.loyalty.services import award_sale_points, reverse_sale_points
from modules.sales.models import Sale

pytestmark = pytest.mark.django_db

SALES_URL = "/api/v2/sales/"
RETURNS_URL = "/api/v2/returns/"


@pytest.fixture
def loyalty_rule(organization):
    return LoyaltyRule.objects.create(
        organization=organization, amount="100.00", points=1, is_active=True
    )


def _sell(client, product, customer, quantity=2):
    response = client.post(
        SALES_URL,
        {
            "payment_method": "CASH",
            "customer": customer.id,
            "items": [{"product": product.id, "quantity": quantity}],
        },
        format="json",
    )
    assert response.status_code == 201, response.data
    return response.data


class TestLoyalty:
    def test_completed_sale_awards_points_once(
        self, authenticated_client, product, customer, loyalty_rule
    ):
        sale = _sell(authenticated_client, product, customer, 2)
        # 2 x 100 = 200 KES → 2 points at 1 / 100
        customer.refresh_from_db()
        assert customer.loyalty_points == 2
        assert LoyaltyLedger.objects.filter(action="EARN").count() == 1

        award_sale_points(Sale.objects.get(pk=sale["id"]))
        customer.refresh_from_db()
        assert customer.loyalty_points == 2
        assert LoyaltyLedger.objects.filter(action="EARN").count() == 1

    def test_return_reverses_points(
        self, authenticated_client, supervisor_client, product, customer, loyalty_rule
    ):
        sale = _sell(authenticated_client, product, customer, 2)
        item_id = sale["items"][0]["id"]
        requested = authenticated_client.post(
            f"{SALES_URL}{sale['id']}/returns/",
            {"reason": "OTHER", "lines": [{"sale_item": item_id, "quantity": 2}]},
            format="json",
        )
        supervisor_client.post(f"{RETURNS_URL}{requested.data['id']}/complete/")
        customer.refresh_from_db()
        assert customer.loyalty_points == 0
        assert LoyaltyLedger.objects.filter(action="REVERSAL").count() == 1

        reverse_sale_points(Sale.objects.get(pk=sale["id"]))
        assert LoyaltyLedger.objects.filter(action="REVERSAL").count() == 1

    def test_redeem_cannot_go_negative(
        self, manager_client, customer, loyalty_rule
    ):
        from modules.loyalty.services import apply_ledger, get_or_create_account

        account = get_or_create_account(customer)
        response = manager_client.post(
            f"/api/v2/loyalty-accounts/{account.pk}/redeem/",
            {"points": 5, "notes": "try"},
            format="json",
        )
        assert response.status_code == 400
        customer.refresh_from_db()
        assert customer.loyalty_points == 0
