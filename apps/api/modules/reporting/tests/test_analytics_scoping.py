import pytest

from modules.sales.models import Sale

ANALYTICS_URL = "/api/v2/analytics/"


@pytest.mark.django_db
class TestAnalyticsAuthorization:
    def test_a_cashier_cannot_read_the_dashboard(self, authenticated_client, product):
        response = authenticated_client.get(f"{ANALYTICS_URL}inventory_status/")

        assert response.status_code == 403

    def test_a_manager_can(self, manager_client, product):
        response = manager_client.get(f"{ANALYTICS_URL}inventory_status/")

        assert response.status_code == 200, response.data

    def test_an_accountant_can(self, api_client, make_user, product):
        user = make_user("accountant1", role="ACCOUNTANT")
        api_client.force_authenticate(user=user)

        response = api_client.get(f"{ANALYTICS_URL}stock_value/")

        assert response.status_code == 200

    def test_anonymous_is_rejected(self, api_client):
        response = api_client.get(f"{ANALYTICS_URL}inventory_status/")

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestAnalyticsScoping:
    def test_inventory_counts_cover_only_the_callers_organization(
        self, manager_client, product, foreign_product
    ):
        """Before phase 4 this aggregate counted every organization's products."""
        response = manager_client.get(f"{ANALYTICS_URL}inventory_status/")

        assert response.status_code == 200, response.data
        assert response.data["total_products"] == 1

    def test_stock_value_excludes_another_organizations_stock(
        self, manager_client, product, foreign_product
    ):
        response = manager_client.get(f"{ANALYTICS_URL}stock_value/")

        # 50 units at 80.00 cost, not the rival's 5 units at 70.00.
        assert float(response.data["total"]) == 4000.0

    def test_the_sales_trend_excludes_another_organizations_sales(
        self, manager_client, rival_user
    ):
        Sale.objects.create(
            sale_number="RIVAL-1",
            cashier=rival_user,
            total_amount="999.00",
            tax_amount="0.00",
            payment_method=Sale.PaymentMethod.CASH,
        )

        response = manager_client.get(f"{ANALYTICS_URL}daily_sales_trend/")

        assert response.status_code == 200, response.data
        assert response.data == []

    def test_the_sales_trend_includes_the_caller_organizations_sales(
        self, manager_client, manager
    ):
        Sale.objects.create(
            sale_number="MINE-1",
            cashier=manager,
            total_amount="250.00",
            tax_amount="0.00",
            payment_method=Sale.PaymentMethod.CASH,
        )

        response = manager_client.get(f"{ANALYTICS_URL}daily_sales_trend/")

        assert response.status_code == 200, response.data
        assert len(response.data) == 1
        assert float(response.data[0]["revenue"]) == 250.0
