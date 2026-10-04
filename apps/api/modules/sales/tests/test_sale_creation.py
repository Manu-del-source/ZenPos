from decimal import Decimal

import pytest

from modules.catalog.models import TaxRate
from modules.inventory.models import StockAdjustment
from modules.sales.models import Sale, SaleItem

SALES_URL = "/api/v2/sales/"


def sale_payload(product, *, sale_number="SALE-1", quantity=2, total_hint=None):
    """The client supplies only what a till knows: the product and the quantity.

    Every monetary value is computed by the server. ``total_hint`` exercises the
    mismatch-detection path, where a client total is a hint, never truth.
    """
    payload = {
        "sale_number": sale_number,
        "payment_method": "CASH",
        "items": [
            {
                "product": product.id,
                "quantity": quantity,
            }
        ],
    }
    if total_hint is not None:
        payload["total_amount"] = total_hint
    return payload


def other_organization_sale(user, *, sale_number="RIVAL-1", total="999.00"):
    return Sale.objects.create(
        sale_number=sale_number,
        cashier=user,
        total_amount=total,
        tax_amount="0.00",
        payment_method=Sale.PaymentMethod.CASH,
    )


@pytest.fixture
def accountant_client(api_client, make_user):
    """An ACCOUNTANT holds reports.view but not sales.create."""
    user = make_user("accountant1", role="ACCOUNTANT")
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
class TestSaleCreation:
    def test_completed_sale_deducts_stock_and_records_a_movement(
        self, authenticated_client, product, cashier
    ):
        response = authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        assert response.status_code == 201, response.data

        product.refresh_from_db()
        assert product.stock_level == 48

        sale = Sale.objects.get()
        assert sale.items.count() == 1

        movement = StockAdjustment.objects.get()
        assert movement.quantity == -2
        assert movement.product_id == product.id
        assert movement.notes == f"Sale {sale.sale_number}"

    def test_insufficient_stock_rejects_and_persists_nothing(
        self, authenticated_client, product
    ):
        response = authenticated_client.post(
            SALES_URL,
            sale_payload(product, quantity=999),
            format="json",
        )

        assert response.status_code == 400
        assert Sale.objects.count() == 0
        assert StockAdjustment.objects.count() == 0

        product.refresh_from_db()
        assert product.stock_level == 50

    def test_cashier_comes_from_the_session_not_the_request_body(
        self, authenticated_client, product, cashier, other_cashier
    ):
        payload = sale_payload(product)
        payload["cashier"] = other_cashier.id

        response = authenticated_client.post(SALES_URL, payload, format="json")

        assert response.status_code == 201, response.data
        # A caller must not be able to attribute a sale to somebody else.
        assert Sale.objects.get().cashier_id == cashier.id

    def test_mpesa_sale_is_rejected_until_payment_is_initiated(self, authenticated_client, product):
        response = authenticated_client.post(
            SALES_URL,
            sale_payload(product, sale_number="SALE-MPESA", quantity=1)
            | {"payment_method": "MPESA"},
            format="json",
        )

        assert response.status_code == 400
        assert "payments endpoint" in str(response.data)
        assert Sale.objects.count() == 0
        product.refresh_from_db()
        assert product.stock_level == 50

    def test_empty_item_list_is_rejected(self, authenticated_client):
        payload = {
            "sale_number": "SALE-EMPTY",
            "payment_method": "CASH",
            "items": [],
        }

        response = authenticated_client.post(SALES_URL, payload, format="json")

        assert response.status_code == 400
        assert Sale.objects.count() == 0

    def test_anonymous_request_is_rejected(self, api_client, product):
        response = api_client.post(SALES_URL, sale_payload(product), format="json")

        assert response.status_code in (401, 403)
        assert Sale.objects.count() == 0

    def test_a_supervisor_can_also_complete_a_sale(self, supervisor_client, product):
        response = supervisor_client.post(SALES_URL, sale_payload(product), format="json")

        assert response.status_code == 201, response.data


@pytest.mark.django_db
class TestServerComputedMoney:
    """The server owns every monetary value on a sale.

    A client that can set a total can set any total, so the serializer resolves
    price, cost and tax from the catalogue and treats a client total as a
    mismatch hint (see docs/plans/phase-5-payments-receipts-audit.md).
    """

    def test_money_is_resolved_from_the_product(self, authenticated_client, product):
        # The fixture product: price 100.00, cost 80.00, no tax band.
        response = authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        assert response.status_code == 201, response.data

        sale = Sale.objects.get()
        assert sale.total_amount == Decimal("200.00")
        assert sale.tax_amount == Decimal("0.00")
        assert sale.discount_amount == Decimal("0.00")

        item = SaleItem.objects.get()
        assert item.unit_price == Decimal("100.00")
        assert item.unit_cost == Decimal("80.00")
        assert item.subtotal == Decimal("200.00")
        assert item.tax_amount == Decimal("0.00")

    def test_inclusive_tax_is_carved_out_of_the_listed_price(
        self, authenticated_client, organization, make_product
    ):
        vat = TaxRate.objects.create(
            organization=organization, name="VAT", rate=Decimal("16.00"), is_inclusive=True
        )
        product = make_product(price=Decimal("116.00"), tax_rate=vat)

        response = authenticated_client.post(
            SALES_URL, sale_payload(product, sale_number="SALE-VAT-IN"), format="json"
        )

        assert response.status_code == 201, response.data

        # The customer pays 116.00; 16.00 of that is VAT and 100.00 is net.
        sale = Sale.objects.get(sale_number="SALE-VAT-IN")
        assert sale.total_amount == Decimal("116.00")
        assert sale.tax_amount == Decimal("16.00")

        item = sale.items.get()
        assert item.subtotal == Decimal("100.00")
        assert item.tax_amount == Decimal("16.00")
        assert item.tax_rate_name == "VAT"
        assert item.tax_rate_percent == Decimal("16.00")

    def test_exclusive_tax_is_added_on_top(
        self, authenticated_client, organization, make_product
    ):
        vat = TaxRate.objects.create(
            organization=organization, name="VAT", rate=Decimal("16.00"), is_inclusive=False
        )
        product = make_product(price=Decimal("100.00"), tax_rate=vat)

        response = authenticated_client.post(
            SALES_URL, sale_payload(product, sale_number="SALE-VAT-EX"), format="json"
        )

        assert response.status_code == 201, response.data

        sale = Sale.objects.get(sale_number="SALE-VAT-EX")
        assert sale.total_amount == Decimal("116.00")
        assert sale.tax_amount == Decimal("16.00")
        assert sale.items.get().subtotal == Decimal("100.00")

    def test_lines_are_rounded_independently_without_drift(
        self, authenticated_client, organization, make_product
    ):
        vat = TaxRate.objects.create(
            organization=organization, name="VAT", rate=Decimal("16.00"), is_inclusive=True
        )
        product = make_product(price=Decimal("33.33"), tax_rate=vat)

        response = authenticated_client.post(
            SALES_URL, sale_payload(product, quantity=3, sale_number="SALE-ROUND"), format="json"
        )

        assert response.status_code == 201, response.data

        sale = Sale.objects.get(sale_number="SALE-ROUND")
        # One line of 3 units: gross 99.99, VAT carved out rounds to 13.79.
        assert sale.total_amount == Decimal("99.99")
        assert sale.tax_amount == Decimal("13.79")
        item = sale.items.get()
        assert item.subtotal + item.tax_amount == sale.total_amount

    def test_a_client_total_that_disagrees_is_rejected(
        self, authenticated_client, product
    ):
        response = authenticated_client.post(
            SALES_URL, sale_payload(product, total_hint="999.00"), format="json"
        )

        assert response.status_code == 400
        assert "200.00" in str(response.data)
        assert Sale.objects.count() == 0
        assert StockAdjustment.objects.count() == 0

        product.refresh_from_db()
        assert product.stock_level == 50

    def test_a_total_hint_within_tolerance_is_accepted_but_not_stored(
        self, authenticated_client, product
    ):
        response = authenticated_client.post(
            SALES_URL, sale_payload(product, total_hint="200.01"), format="json"
        )

        assert response.status_code == 201, response.data
        # The server's figure is stored, not the client's.
        assert Sale.objects.get().total_amount == Decimal("200.00")

    def test_a_garbage_total_hint_is_rejected(self, authenticated_client, product):
        response = authenticated_client.post(
            SALES_URL, sale_payload(product, total_hint="not-a-number"), format="json"
        )

        assert response.status_code == 400
        assert Sale.objects.count() == 0

    def test_client_sent_line_money_is_ignored(self, authenticated_client, product):
        payload = sale_payload(product)
        payload["items"][0].update({"unit_price": "1.00", "subtotal": "1.00"})
        payload["tax_amount"] = "77.00"

        response = authenticated_client.post(SALES_URL, payload, format="json")

        assert response.status_code == 201, response.data
        assert Sale.objects.get().total_amount == Decimal("200.00")
        item = SaleItem.objects.get()
        assert item.unit_price == Decimal("100.00")
        assert item.subtotal == Decimal("200.00")

    def test_zero_and_negative_quantities_are_rejected(self, authenticated_client, product):
        for quantity in (0, -2):
            response = authenticated_client.post(
                SALES_URL,
                sale_payload(product, quantity=quantity, sale_number=f"SALE-Q{quantity}"),
                format="json",
            )
            assert response.status_code == 400, quantity

        assert Sale.objects.count() == 0


@pytest.mark.django_db
class TestSalePermissions:
    def test_an_accountant_cannot_create_a_sale(self, accountant_client, product):
        response = accountant_client.post(SALES_URL, sale_payload(product), format="json")

        assert response.status_code == 403
        assert Sale.objects.count() == 0

    def test_an_accountant_can_read_the_sales_they_reconcile(self, accountant_client, product):
        response = accountant_client.get(SALES_URL)

        assert response.status_code == 200


@pytest.mark.django_db
class TestSalesAreAppendOnly:
    """A completed sale is a financial record, not an editable document."""

    def test_a_completed_sale_cannot_be_edited(self, authenticated_client, product):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        response = authenticated_client.patch(
            f"{SALES_URL}{created.data['id']}/", {"total_amount": "1.00"}, format="json"
        )

        assert response.status_code == 405
        assert Sale.objects.get().total_amount == Decimal("200.00")

    def test_a_completed_sale_cannot_be_deleted(self, authenticated_client, product):
        created = authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        response = authenticated_client.delete(f"{SALES_URL}{created.data['id']}/")

        assert response.status_code == 405
        assert Sale.objects.count() == 1


@pytest.mark.django_db
class TestSalesTenantBoundary:
    def test_another_organizations_product_cannot_be_sold(
        self, authenticated_client, foreign_product
    ):
        response = authenticated_client.post(
            SALES_URL, sale_payload(foreign_product), format="json"
        )

        assert response.status_code == 400
        assert Sale.objects.count() == 0

        foreign_product.refresh_from_db()
        assert foreign_product.stock_level == 5

    def test_a_sale_cannot_mix_organizations(
        self, authenticated_client, product, foreign_product
    ):
        payload = sale_payload(product)
        payload["items"].append({"product": foreign_product.id, "quantity": 1})

        response = authenticated_client.post(SALES_URL, payload, format="json")

        assert response.status_code == 400
        assert Sale.objects.count() == 0

    def test_another_organizations_sales_are_invisible(
        self, authenticated_client, rival_user
    ):
        other_organization_sale(rival_user)

        response = authenticated_client.get(SALES_URL)

        assert response.data["count"] == 0


@pytest.mark.django_db
class TestSalesReport:
    def test_report_totals_reflect_completed_sales(
        self, authenticated_client, admin_client, product
    ):
        authenticated_client.post(SALES_URL, sale_payload(product), format="json")

        response = admin_client.get(f"{SALES_URL}reports/?range=today")

        assert response.status_code == 200, response.data
        assert response.data["total_sales"] == 1
        assert float(response.data["total_revenue"]) == 200.0
        assert response.data["top_products"][0]["product__name"] == product.name

    def test_report_requires_reports_view(self, authenticated_client, product):
        response = authenticated_client.get(f"{SALES_URL}reports/?range=today")

        assert response.status_code == 403

    def test_report_excludes_another_organizations_sales(
        self, manager_client, rival_user
    ):
        other_organization_sale(rival_user)

        response = manager_client.get(f"{SALES_URL}reports/?range=today")

        assert response.status_code == 200, response.data
        assert response.data["total_sales"] == 0
        assert float(response.data["total_revenue"]) == 0.0
