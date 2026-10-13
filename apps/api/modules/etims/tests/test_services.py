"""Service-layer tests: issuance, cancellation and the adapter seam.

A sale is created through the real sales API — the tax snapshots on its
lines are what the invoice documents, and those snapshots only exist when
the sale went through the server's money path.
"""

from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from modules.catalog.models import Product, TaxRate
from modules.core.models import AuditLog
from modules.etims.base import EtimsAdapter
from modules.etims.models import EtimsDevice, EtimsInvoice
from modules.etims.services import (
    cancel_invoice_for_sale,
    get_etims_adapter,
    issue_invoice_for_sale,
)
from modules.sales.models import Sale


def _cash_sale(client, items):
    """Create a cash sale through the real sales API and return it.

    The server generates the sale number; tests identify their sale by the
    returned primary key, never by number.
    """
    response = client.post(
        "/api/v2/sales/",
        {"payment_method": "CASH", "items": items},
        format="json",
    )
    assert response.status_code == 201, response.data
    return Sale.objects.get(pk=response.data["id"])


def _vat_product(organization, name="Butter 200g", rate="16.00"):
    # Kenyan shelf prices carry the VAT: the listed price already contains it.
    vat = TaxRate.objects.create(
        organization=organization,
        name="VAT",
        rate=rate,
        is_inclusive=True,
    )
    return Product.objects.create(
        organization=organization,
        name=name,
        sku="BUTTER-200",
        price="150.00",
        cost_price="110.00",
        tax_rate=vat,
        stock_level=40,
    )


@pytest.mark.django_db
class TestIssueInvoice:
    def test_issue_is_idempotent(self, authenticated_client, product, manager):
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 2}])

        first = issue_invoice_for_sale(sale=sale)
        again = issue_invoice_for_sale(sale=sale)

        assert again.pk == first.pk
        assert EtimsInvoice.objects.filter(sale=sale).count() == 1
        assert AuditLog.objects.filter(action="etims.invoice_issued").count() == 1

    def test_invoice_snapshots_the_sale_as_rung(self, authenticated_client, product, organization):
        """Lines and per-rate tax come from the persisted snapshots, not the
        catalogue, and money values are strings in the stored document."""
        vat_product = _vat_product(organization)
        sale = _cash_sale(
            authenticated_client,
            [
                {"product": product.id, "quantity": 2},  # no tax: 2 x 100.00
                {"product": vat_product.id, "quantity": 3},  # 16% on 150.00
            ],
        )

        invoice = issue_invoice_for_sale(sale=sale)

        assert invoice.status == EtimsInvoice.Status.ISSUED
        assert invoice.uin == ""  # assigned by KRA, never by this system
        assert invoice.issued_at is not None
        assert invoice.currency == "KES"
        # Inclusive VAT on 3 x 150.00: tax = 450 x 16 / 116 = 62.07.
        assert invoice.subtotal == Decimal("587.93")
        assert invoice.tax_amount == Decimal("62.07")
        assert invoice.total_amount == Decimal("650.00")

        by_name = {line["name"]: line for line in invoice.line_items}
        assert set(by_name) == {"Milk 1L", "Butter 200g"}
        assert by_name["Milk 1L"] == {
            "name": "Milk 1L",
            "quantity": 2,
            "unit_price": "100.00",
            "subtotal": "200.00",
            "tax_rate_name": "",
            "tax_rate_percent": None,
            "tax_amount": "0.00",
            "line_total": "200.00",
        }
        assert by_name["Butter 200g"]["tax_rate_name"] == "VAT"
        assert by_name["Butter 200g"]["tax_rate_percent"] == "16.00"
        assert by_name["Butter 200g"]["subtotal"] == "387.93"
        assert by_name["Butter 200g"]["tax_amount"] == "62.07"
        assert by_name["Butter 200g"]["line_total"] == "450.00"

        # Grouped per rate, in rung-up order: the untaxed band first.
        assert [group["name"] for group in invoice.tax_breakdown] == [
            "No tax",
            "VAT",
        ]
        vat_group = invoice.tax_breakdown[1]
        assert vat_group == {
            "name": "VAT",
            "rate": "16.00",
            "net": "387.93",
            "tax": "62.07",
        }

    def test_snapshot_survives_catalogue_change(self, authenticated_client, product, organization):
        """A later price or rate change rewrites the invoice no more than it
        rewrites the receipt: the document is what was rung, not the
        catalogue's current state."""
        vat_product = _vat_product(organization)
        sale = _cash_sale(
            authenticated_client,
            [
                {"product": product.id, "quantity": 1},
                {"product": vat_product.id, "quantity": 1},
            ],
        )
        invoice = issue_invoice_for_sale(sale=sale)
        issued_lines = invoice.line_items
        issued_breakdown = invoice.tax_breakdown
        issued_total = invoice.total_amount

        product.price = "999.00"
        product.save(update_fields=["price"])
        vat_product.tax_rate.rate = Decimal("20.00")
        vat_product.tax_rate.save(update_fields=["rate"])
        product.tax_rate = vat_product.tax_rate
        product.save(update_fields=["tax_rate"])

        invoice.refresh_from_db()

        assert invoice.line_items == issued_lines
        assert invoice.tax_breakdown == issued_breakdown
        assert invoice.total_amount == issued_total

    def test_issue_stores_the_device_it_was_rung_on(
        self, authenticated_client, product, organization
    ):
        device = EtimsDevice.objects.create(
            organization=organization,
            name="Westlands ERS",
            kda_pin="P051234567X",
            device_number="KEN-ERS-0001",
        )
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])

        invoice = issue_invoice_for_sale(sale=sale, device=device)

        assert invoice.device_id == device.id


@pytest.mark.django_db
class TestCancelInvoice:
    def test_cancel_transitions_and_keeps_the_document(
        self, authenticated_client, product, manager
    ):
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 2}])
        invoice = issue_invoice_for_sale(sale=sale)
        lines = invoice.line_items

        cancelled = cancel_invoice_for_sale(sale=sale, reason="Sale voided at till", actor=manager)

        assert cancelled.pk == invoice.pk
        assert cancelled.status == EtimsInvoice.Status.CANCELLED
        assert cancelled.cancelled_at is not None
        assert cancelled.cancellation_reason == "Sale voided at till"
        # The document itself is kept: history must stay explainable.
        assert cancelled.line_items == lines
        assert cancelled.total_amount == invoice.total_amount

        row = AuditLog.objects.get(action="etims.invoice_cancelled")
        assert row.actor_id == manager.id
        assert row.entity_type == "etims_invoice"
        assert row.entity_id == str(invoice.pk)

    def test_cancel_without_an_invoice_is_a_noop(self, authenticated_client, product):
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])

        assert cancel_invoice_for_sale(sale=sale, reason="x") is None

        assert EtimsInvoice.objects.count() == 0
        assert AuditLog.objects.filter(action="etims.invoice_cancelled").count() == 0

    def test_cancelling_twice_records_one_cancellation(
        self, authenticated_client, product, manager
    ):
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])
        invoice = issue_invoice_for_sale(sale=sale)

        first = cancel_invoice_for_sale(sale=sale, reason="first", actor=manager)
        second = cancel_invoice_for_sale(sale=sale, reason="second", actor=manager)

        assert first.pk == invoice.pk
        assert second is None
        assert AuditLog.objects.filter(action="etims.invoice_cancelled").count() == 1
        invoice.refresh_from_db()
        assert invoice.cancellation_reason == "first"


@pytest.mark.django_db
class TestAdapterSeam:
    """The adapter is the only place transmission will ever live, so the
    contract it has with the domain is tested here against a fake that
    records what it was asked to do — including stamping a UIN, which only
    a KRA-side answer may produce."""

    class RecordingAdapter(EtimsAdapter):
        adapter_name = "recording-fake"

        def __init__(self):
            self.issued = []
            self.cancelled = []

        def issue(self, *, invoice):
            self.issued.append(invoice)
            invoice.uin = "FAKE-UIN-1"
            invoice.save(update_fields=["uin"])

        def cancel(self, *, invoice):
            self.cancelled.append(invoice)

    def test_issue_invokes_the_adapter_and_keeps_its_uin(self, authenticated_client, product):
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])
        adapter = self.RecordingAdapter()

        invoice = issue_invoice_for_sale(sale=sale, adapter=adapter)

        assert [inv.pk for inv in adapter.issued] == [invoice.pk]
        assert invoice.uin == "FAKE-UIN-1"

        # Cancelling goes through the same adapter, and the UIN survives:
        # the document stays traceable to what the authority saw.
        cancelled = cancel_invoice_for_sale(sale=sale, reason="void", adapter=adapter)
        assert cancelled.uin == "FAKE-UIN-1"

    def test_default_adapter_records_locally_and_sends_nothing(self, authenticated_client, product):
        """With the production adapter, no UIN is ever invented and nothing
        leaves the machine."""
        adapter = get_etims_adapter()
        assert adapter.adapter_name == "local"

        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])
        invoice = issue_invoice_for_sale(sale=sale)
        cancel_invoice_for_sale(sale=sale, reason="void")

        invoice.refresh_from_db()
        assert invoice.uin == ""
        assert invoice.status == EtimsInvoice.Status.CANCELLED


@pytest.mark.django_db
class TestDeviceModel:
    def test_device_is_unique_per_organization_name(self, organization, other_organization):
        EtimsDevice.objects.create(
            organization=organization, name="Till ERS", kda_pin="P051234567X"
        )
        duplicate = EtimsDevice(organization=organization, name="Till ERS", kda_pin="P051234567X")
        # The savepoint keeps the aborted statement from poisoning the
        # test's surrounding transaction.
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                duplicate.save()

        # The same name in another tenant is a different device.
        other = EtimsDevice(organization=other_organization, name="Till ERS", kda_pin="P0987654321")
        other.save()

    def test_invoice_protects_its_sale(self, authenticated_client, product):
        """Deleting a sale with an invoice is refused: an orphaned compliance
        document would describe money with no ledger behind it."""
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])
        issue_invoice_for_sale(sale=sale)

        with pytest.raises(IntegrityError):
            Sale.objects.filter(pk=sale.pk).delete()
