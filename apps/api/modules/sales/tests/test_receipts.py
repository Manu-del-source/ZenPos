"""Tests for receipt rendering: HTML reprint and thermal text.

Receipts must render recorded truth — computed totals, per-rate tax groups and
the payment rows — and must respect the tenant boundary.
"""

from decimal import Decimal

import pytest

from modules.catalog.models import TaxRate
from modules.payments.models import Payment
from modules.sales.models import Sale
from modules.sales.receipts import build_receipt_context, render_thermal_receipt

SALES_URL = "/api/v2/sales/"
RECEIPT_URL = "/api/v2/sales/{id}/receipt/"


def create_sale_via_api(client, product, *, sale_number="SALE-R1", quantity=2):
    return client.post(
        SALES_URL,
        {
            "sale_number": sale_number,
            "payment_method": "CASH",
            "items": [{"product": product.id, "quantity": quantity}],
        },
        format="json",
    )


@pytest.mark.django_db
class TestReceiptHtml:
    def test_receipt_shows_computed_totals(self, authenticated_client, product):
        created = create_sale_via_api(authenticated_client, product)
        assert created.status_code == 201, created.data
        sale = Sale.objects.get()

        response = authenticated_client.get(RECEIPT_URL.format(id=sale.id))

        assert response.status_code == 200
        body = response.content.decode()
        assert sale.sale_number in body
        assert "200.00" in body  # 2 x 100.00, no tax band
        assert "TOTAL" in body

    def test_receipt_groups_tax_per_rate(
        self, authenticated_client, organization, make_product
    ):
        vat = TaxRate.objects.create(
            organization=organization, name="VAT", rate=Decimal("16.00"), is_inclusive=True
        )
        standard = make_product(price=Decimal("116.00"), tax_rate=vat)
        zero_rated = make_product(name="Brown Bread", price=Decimal("50.00"))
        authenticated_client.post(
            SALES_URL,
            {
                "sale_number": "SALE-TAXGROUP",
                "payment_method": "CASH",
                "items": [
                    {"product": standard.id, "quantity": 1},
                    {"product": zero_rated.id, "quantity": 1},
                ],
            },
            format="json",
        )
        sale = Sale.objects.get()

        response = authenticated_client.get(RECEIPT_URL.format(id=sale.id))

        assert response.status_code == 200
        body = response.content.decode()
        # Both rate groups appear with their net/tax figures.
        assert "VAT (16.00%)" in body
        assert "No tax" in body

    def test_receipt_shows_the_provider_reference_for_mpesa(
        self, authenticated_client, product, cashier
    ):
        created = create_sale_via_api(authenticated_client, product)
        assert created.status_code == 201, created.data
        sale = Sale.objects.get()

        Payment.objects.create(
            sale=sale,
            method=Payment.Method.MPESA,
            amount=sale.total_amount,
            status=Payment.Status.COMPLETED,
            provider_reference="QK71HLN2X9",
        )

        response = authenticated_client.get(RECEIPT_URL.format(id=sale.id))

        assert response.status_code == 200
        assert "QK71HLN2X9" in response.content.decode()

    def test_another_organizations_receipt_is_a_404(self, authenticated_client, rival_user):
        sale = Sale.objects.create(
            sale_number="RIVAL-R1",
            cashier=rival_user,
            total_amount=Decimal("10.00"),
            tax_amount=Decimal("0.00"),
            payment_method=Sale.PaymentMethod.CASH,
        )

        response = authenticated_client.get(RECEIPT_URL.format(id=sale.id))

        assert response.status_code == 404

    def test_thermal_format_serves_plain_text_within_column_width(
        self, authenticated_client, product
    ):
        created = create_sale_via_api(authenticated_client, product)
        assert created.status_code == 201, created.data
        sale = Sale.objects.get()

        response = authenticated_client.get(
            RECEIPT_URL.format(id=sale.id) + "?output=thermal"
        )

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/plain")
        lines = response.content.decode().splitlines()
        assert all(len(line) <= 42 for line in lines)
        assert "TOTAL" in "\n".join(lines)


@pytest.mark.django_db
class TestThermalRenderer:
    def make_sale(self, cashier, product):
        return Sale.objects.create(
            sale_number="SALE-THERMAL",
            cashier=cashier,
            total_amount=Decimal("200.00"),
            tax_amount=Decimal("0.00"),
            payment_method=Sale.PaymentMethod.CASH,
        )

    def test_money_is_right_aligned_at_the_column_edge(self, product, cashier):
        sale = self.make_sale(cashier, product)
        context = build_receipt_context(sale)

        text = render_thermal_receipt(context, columns=42)

        total_line = next(line for line in text.splitlines() if "TOTAL" in line)
        assert total_line.endswith("200.00")
        assert len(total_line) == 42

    def test_long_names_are_truncated_not_wrapped(self, product, cashier):
        sale = self.make_sale(cashier, product)
        context = build_receipt_context(sale)
        context["items"] = [
            {
                "name": "A very long product name that will not fit on one line at all",
                "quantity": 1,
                "unit_price": Decimal("1.00"),
                "line_total": Decimal("1.00"),
            }
        ]

        text = render_thermal_receipt(context, columns=42)

        for line in text.splitlines():
            assert len(line) <= 42
