"""Customer directory: tenant scoping, search, archiving, points balance."""

import pytest
from rest_framework.test import APIClient

from modules.loyalty.models import LoyaltyLedger
from modules.loyalty.services import apply_ledger

from ..models import Customer

pytestmark = pytest.mark.django_db

CUSTOMERS_URL = "/api/v2/customers/"


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestDirectory:
    def test_a_cashier_lists_and_creates_customers(self, authenticated_client):
        response = authenticated_client.post(
            CUSTOMERS_URL,
            {"name": "Amina Otieno", "phone": "0722999001"},
            format="json",
        )
        assert response.status_code == 201, response.data
        assert response.data["points_balance"] == 0

        listing = authenticated_client.get(CUSTOMERS_URL)
        assert listing.status_code == 200
        assert any(row["name"] == "Amina Otieno" for row in listing.data["results"])

    def test_phones_are_unique_per_organization(self, authenticated_client, rival_user):
        first = authenticated_client.post(
            CUSTOMERS_URL,
            {"name": "Jane Wanjiru", "phone": "0722000001"},
            format="json",
        )
        assert first.status_code == 201, first.data
        # Same phone, same shop: rejected.
        duplicate = authenticated_client.post(
            CUSTOMERS_URL,
            {"name": "Jane Wanjiru (copy)", "phone": "0722000001"},
            format="json",
        )
        assert duplicate.status_code == 400, duplicate.data

        # Same phone, a different shop: allowed — the same person can shop
        # at two businesses.
        rival_client = _client_for(rival_user)
        other = rival_client.post(
            CUSTOMERS_URL,
            {"name": "Jane Wanjiru", "phone": "0722000001"},
            format="json",
        )
        assert other.status_code == 201, other.data

    def test_another_organization_customers_are_invisible(
        self, authenticated_client, rival_user, customer
    ):
        rival_client = _client_for(rival_user)
        listing = rival_client.get(CUSTOMERS_URL)
        assert listing.status_code == 200
        assert all(row["id"] != customer.id for row in listing.data["results"])

        retrieve = rival_client.get(f"{CUSTOMERS_URL}{customer.id}/")
        assert retrieve.status_code == 404

        search = rival_client.get(f"{CUSTOMERS_URL}search/", {"phone": customer.phone})
        assert search.status_code == 404

    def test_search_finds_a_customer_by_phone(self, authenticated_client, customer):
        response = authenticated_client.get(f"{CUSTOMERS_URL}search/", {"phone": customer.phone})
        assert response.status_code == 200, response.data
        assert response.data["id"] == customer.id

        miss = authenticated_client.get(f"{CUSTOMERS_URL}search/", {"phone": "0700000000"})
        assert miss.status_code == 404


class TestArchiving:
    def test_delete_archives_instead_of_deleting(self, manager_client, customer):
        response = manager_client.delete(f"{CUSTOMERS_URL}{customer.id}/")
        assert response.status_code == 200, response.data

        # Gone from the directory...
        listing = manager_client.get(CUSTOMERS_URL).data["results"]
        assert customer.id not in [row["id"] for row in listing]
        assert manager_client.get(f"{CUSTOMERS_URL}{customer.id}/").status_code == 404
        assert (
            manager_client.get(f"{CUSTOMERS_URL}search/", {"phone": customer.phone}).status_code
            == 404
        )

        # ...but the row survives, so the sales history keeps explaining itself.
        assert Customer.all_objects.get(pk=customer.pk).deleted_at is not None

    def test_archiving_a_customer_keeps_their_sales_readable(
        self, manager_client, authenticated_client, customer, product
    ):
        sale = authenticated_client.post(
            "/api/v2/sales/",
            {
                "payment_method": "CASH",
                "customer": customer.id,
                "items": [{"product": product.id, "quantity": 1}],
            },
            format="json",
        )
        assert sale.status_code == 201, sale.data

        assert manager_client.delete(f"{CUSTOMERS_URL}{customer.id}/").status_code == 200

        listing = authenticated_client.get("/api/v2/sales/")
        assert listing.status_code == 200
        rows = [row for row in listing.data["results"] if row["id"] == sale.data["id"]]
        assert rows and rows[0]["customer"] is not None

    def test_a_phone_can_be_reused_after_archiving(
        self, manager_client, authenticated_client, customer
    ):
        assert manager_client.delete(f"{CUSTOMERS_URL}{customer.id}/").status_code == 200

        replacement = authenticated_client.post(
            CUSTOMERS_URL,
            {"name": "New Jane", "phone": customer.phone},
            format="json",
        )
        assert replacement.status_code == 201, replacement.data


class TestPointsBalance:
    def test_the_balance_is_the_ledgers_balance(self, manager_client, customer, organization):
        entry = apply_ledger(
            customer=customer,
            points=7,
            action=LoyaltyLedger.Action.ADJUST,
            organization=organization,
            notes="Loyalty program launch credit.",
        )
        assert entry is not None

        response = manager_client.get(f"{CUSTOMERS_URL}{customer.id}/")
        assert response.status_code == 200
        assert response.data["points_balance"] == 7
