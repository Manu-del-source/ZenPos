"""Invoice issuance and cancellation, atomic with the audit that explains them.

A sale has at most one eTIMS invoice, and issuing is idempotent: the invoice
is a document number, not an action. The document is built from
``build_receipt_context`` — the same source the receipt prints — so an
invoice and its printed receipt can never disagree, and both read persisted
rows only.
"""

from django.db import transaction
from django.utils import timezone

from modules.core.audit import record_audit
from modules.sales.receipts import build_receipt_context

from .base import EtimsAdapter, LocalRecordingAdapter
from .models import EtimsInvoice


def get_etims_adapter() -> EtimsAdapter:
    """One construction site, like the payment provider (ADR-0005, ADR-0012).

    Until the KRA transmission endpoints are verified against official
    documentation (ADR-0019) this returns the recording-only adapter: every
    invoice is real, reconcilable and auditable, and nothing is transmitted.
    """
    return LocalRecordingAdapter()


def invoice_line_items(sale) -> list[dict]:
    """The document's lines, from persisted rows only.

    Money values are strings: the JSON snapshot stores no Decimal, and the
    string form is what both the receipt and any future transmission
    payload print, so the snapshot cannot drift from either.
    """
    return [
        {
            "name": item.product.name,
            "quantity": item.quantity,
            "unit_price": str(item.unit_price),
            "subtotal": str(item.subtotal),
            "tax_rate_name": item.tax_rate_name,
            "tax_rate_percent": (
                None if item.tax_rate_percent is None else str(item.tax_rate_percent)
            ),
            "tax_amount": str(item.tax_amount),
            "line_total": str(item.subtotal + item.tax_amount),
        }
        for item in sale.items.all()
    ]


def issue_invoice_for_sale(*, sale, device=None, adapter=None) -> EtimsInvoice:
    """Record the eTIMS invoice for a sale — exactly one, forever.

    Idempotent on purpose: a sale that already has an invoice gets it back,
    so a retried trigger (or a backfill run twice) cannot produce a second
    document for one sale. The line and tax snapshots are persisted on the
    row: a later catalogue or rate change rewrites the invoice no more than
    it rewrites the receipt.
    """
    existing = EtimsInvoice.objects.filter(sale=sale).first()
    if existing is not None:
        return existing

    context = build_receipt_context(sale)
    adapter = adapter or get_etims_adapter()
    with transaction.atomic():
        invoice = EtimsInvoice.objects.create(
            sale=sale,
            device=device,
            status=EtimsInvoice.Status.ISSUED,
            issued_at=timezone.now(),
            line_items=invoice_line_items(sale),
            tax_breakdown=[
                {
                    "name": group["name"],
                    "rate": None if group["rate"] is None else str(group["rate"]),
                    "net": str(group["net"]),
                    "tax": str(group["tax"]),
                }
                for group in context["tax_groups"]
            ],
            subtotal=context["subtotal"],
            tax_amount=context["tax_amount"],
            total_amount=context["total_amount"],
            currency=context["currency"],
        )
        adapter.issue(invoice=invoice)
        record_audit(
            action="etims.invoice_issued",
            entity_type="etims_invoice",
            entity_id=invoice.pk,
            after={
                "sale": sale.sale_number,
                "total": str(invoice.total_amount),
                "adapter": adapter.adapter_name,
            },
        )
    return invoice


def cancel_invoice_for_sale(
    *, sale, reason: str = "", actor=None, request=None, adapter=None
) -> EtimsInvoice | None:
    """Cancel the sale's invoice when the sale is voided.

    A voided sale must not leave an ISSUED invoice behind: the document
    would describe money the shop no longer holds. The transition is the
    whole correction — the row and its snapshots are kept, with the reason
    — so the document's history still explains itself. A sale with no
    invoice, or one already cancelled, is a no-op.
    """
    invoice = EtimsInvoice.objects.filter(sale=sale).first()
    if invoice is None or invoice.status != EtimsInvoice.Status.ISSUED:
        return None

    adapter = adapter or get_etims_adapter()
    with transaction.atomic():
        adapter.cancel(invoice=invoice)
        invoice.status = EtimsInvoice.Status.CANCELLED
        invoice.cancelled_at = timezone.now()
        invoice.cancellation_reason = reason[:255]
        invoice.save(update_fields=["status", "cancelled_at", "cancellation_reason", "updated_at"])
        record_audit(
            action="etims.invoice_cancelled",
            entity_type="etims_invoice",
            entity_id=invoice.pk,
            actor=actor,
            request=request,
            before={"status": EtimsInvoice.Status.ISSUED},
            after={
                "status": invoice.status,
                "sale": sale.sale_number,
                "reason": reason[:255],
            },
        )
    return invoice
