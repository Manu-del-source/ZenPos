import pytest

from modules.inventory.models import StockAdjustment

ADJUSTMENTS_URL = "/api/v2/adjustments/"


def adjustment_payload(product, *, quantity, type_="RESTOCK"):
    return {
        "product": product.id,
        "quantity": quantity,
        "type": type_,
        "notes": "Delivery from supplier",
    }


@pytest.mark.django_db
class TestStockAdjustments:
    def test_adjusting_stock_requires_the_adjust_permission(self, authenticated_client, product):
        """A CASHIER may see stock but not change it."""
        response = authenticated_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(product, quantity=25),
            format="json",
        )

        assert response.status_code == 403
        assert StockAdjustment.objects.count() == 0

        product.refresh_from_db()
        assert product.stock_level == 50

    def test_positive_adjustment_increases_stock(self, supervisor_client, product):
        response = supervisor_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(product, quantity=25),
            format="json",
        )

        assert response.status_code == 201, response.data
        product.refresh_from_db()
        assert product.stock_level == 75

    def test_negative_adjustment_decreases_stock(self, supervisor_client, product):
        response = supervisor_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(product, quantity=-5, type_="DAMAGE"),
            format="json",
        )

        assert response.status_code == 201, response.data
        product.refresh_from_db()
        assert product.stock_level == 45
        assert StockAdjustment.objects.get().type == "DAMAGE"

    def test_actor_is_taken_from_the_session(
        self, supervisor_client, supervisor, other_cashier, product
    ):
        payload = adjustment_payload(product, quantity=1)
        payload["user"] = other_cashier.id

        response = supervisor_client.post(ADJUSTMENTS_URL, payload, format="json")

        assert response.status_code == 201, response.data
        assert StockAdjustment.objects.get().user_id == supervisor.id

    def test_anonymous_request_is_rejected(self, api_client, product):
        response = api_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(product, quantity=1),
            format="json",
        )

        assert response.status_code in (401, 403)
        assert StockAdjustment.objects.count() == 0


@pytest.mark.django_db
class TestAdjustmentsAreAppendOnly:
    """An adjustment explains a stock change that has already happened.

    Editing or deleting it would leave the stock level unexplainable, so the
    correction path is a reversing adjustment, not a rewrite.
    """

    def test_an_existing_adjustment_cannot_be_edited(self, supervisor_client, product):
        created = supervisor_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(product, quantity=10),
            format="json",
        )
        adjustment_id = created.data["id"]

        response = supervisor_client.patch(
            f"{ADJUSTMENTS_URL}{adjustment_id}/", {"quantity": 500}, format="json"
        )

        assert response.status_code == 405
        product.refresh_from_db()
        assert product.stock_level == 60

    def test_an_existing_adjustment_cannot_be_deleted(self, supervisor_client, product):
        created = supervisor_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(product, quantity=10),
            format="json",
        )

        response = supervisor_client.delete(f"{ADJUSTMENTS_URL}{created.data['id']}/")

        assert response.status_code == 405
        assert StockAdjustment.objects.count() == 1

    def test_movements_are_listed_but_not_editable(self, supervisor_client, product):
        supervisor_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(product, quantity=10),
            format="json",
        )

        response = supervisor_client.get(ADJUSTMENTS_URL)

        assert response.status_code == 200
        assert response.data["count"] == 1


@pytest.mark.django_db
class TestAdjustmentTenantBoundary:
    def test_another_organizations_product_cannot_be_adjusted(
        self, supervisor_client, foreign_product
    ):
        """Queryset scoping stops them reading it; this stops them writing to it."""
        response = supervisor_client.post(
            ADJUSTMENTS_URL,
            adjustment_payload(foreign_product, quantity=5),
            format="json",
        )

        assert response.status_code == 400
        assert "product" in response.data

        foreign_product.refresh_from_db()
        assert foreign_product.stock_level == 5

    def test_another_organizations_adjustments_are_invisible(
        self, supervisor_client, supervisor, foreign_product
    ):
        StockAdjustment.objects.create(
            product=foreign_product,
            user=supervisor,
            quantity=5,
            type=StockAdjustment.AdjustmentType.RESTOCK,
        )

        response = supervisor_client.get(ADJUSTMENTS_URL)

        assert response.data["count"] == 0
