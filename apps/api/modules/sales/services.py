"""Sale lifecycle: giving stock back, and voiding a sale.

Two flows return stock to the shelf, and both must happen **exactly once**:

* a failed or unanswered M-Pesa payment releases the reservation it held
  (``payments.services.release_mpesa_stock_reservation`` calls in here);
* a voided sale restores whatever it took — the reservation for an unpaid
  M-Pesa sale, or the final deduction for a cash sale.

Idempotency cannot live in the caller. A callback can be redelivered, a
supervisor can double-tap, and a retried request can arrive twice, so it is
derived from the ledger itself: everything a sale took is a negative
``StockAdjustment`` whose notes begin with the sale number, everything given
back is a positive row under the same prefix, and only the difference is
outstanding. Re-running the restore with nothing outstanding is a no-op.
"""

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from modules.core.audit import record_audit
from modules.inventory.models import StockAdjustment

from .models import Sale


def sale_note_prefix(sale) -> str:
    """The notes prefix shared by every stock movement belonging to a sale."""
    return f"Sale {sale.sale_number}"


def _movements_for_sale(sale):
    """``(taken_by_product, restored_by_product)`` as UUID -> positive ints.

    Rows are matched on the sale number *and* the separator that sale creation
    writes, so ``SALE-1`` never picks up movements belonging to ``SALE-12``.
    """
    prefix = sale_note_prefix(sale)
    rows = StockAdjustment.objects.filter(notes=prefix) | StockAdjustment.objects.filter(
        notes__startswith=f"{prefix} -"
    )

    taken: dict = defaultdict(int)
    restored: dict = defaultdict(int)
    for row in rows.only("product_id", "quantity"):
        if row.quantity < 0:
            taken[row.product_id] += -row.quantity
        else:
            restored[row.product_id] += row.quantity
    return taken, restored


def outstanding_stock_for_sale(sale) -> int:
    """How much stock this sale still owes the shelf, across all its lines."""
    taken, restored = _movements_for_sale(sale)
    return sum(
        max(0, quantity - restored.get(product_id, 0))
        for product_id, quantity in taken.items()
    )


@transaction.atomic
def restore_sale_stock(
    *,
    sale,
    actor=None,
    request=None,
    reason: str = "",
    audit_action: str = "stock.restored",
) -> int:
    """Return everything the sale still owes, exactly once, and report how much.

    The sale row is locked for the duration, so two concurrent restores (a
    callback and a supervisor's void, say) cannot both read the same
    outstanding quantity and both apply it.
    """
    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    taken, restored = _movements_for_sale(sale)

    released = 0
    for product_id, quantity in taken.items():
        owed = quantity - restored.get(product_id, 0)
        if owed <= 0:
            continue

        # Imported here rather than at module level: catalog sits above sales in
        # the dependency order, and the import direction rule is worth keeping
        # honest even where Python would allow the shortcut.
        from modules.catalog.models import Product

        product = Product.objects.select_for_update().get(pk=product_id)
        product.stock_level += owed
        product.save(update_fields=["stock_level", "updated_at"])
        StockAdjustment.objects.create(
            product=product,
            user=actor,
            quantity=owed,
            type=StockAdjustment.AdjustmentType.RETURN,
            notes=f"{sale_note_prefix(sale)} - stock restored ({reason or 'released'})",
        )
        released += owed

    if released:
        record_audit(
            action=audit_action,
            entity_type="sale",
            entity_id=sale.pk,
            actor=actor,
            request=request,
            after={"sale": sale.sale_number, "quantity": released, "reason": reason},
        )
    return released


@transaction.atomic
def reserve_sale_stock(*, sale, actor=None, request=None, reason: str = "") -> int:
    """Put a sale's stock back on hold when it is not held any more.

    The mirror of :func:`restore_sale_stock`, and the reason it is needed: a
    customer whose STK prompt fails is not refused a second try. The failed
    attempt gave the stock back, so a retry that only re-pushed the payment
    would complete a sale whose shelf movement had already been reversed — the
    shop would have taken the money and still show the item as sellable.

    Only lines the sale is no longer holding are taken, so re-running this is
    harmless, and a sale with no outstanding shortfall (the first attempt, or a
    sale already deducted) is left untouched. Stock that is no longer there is
    a refusal, not an oversell: the caller must not push a payment for goods
    the shop cannot hand over.
    """
    from modules.payments.base import PaymentGatewayError
    from modules.payments.models import Payment

    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status == Sale.Status.VOIDED:
        raise PaymentGatewayError("This sale has been voided.")

    if Payment.objects.filter(sale=sale, status=Payment.Status.COMPLETED).exists():
        # Settled money owns its deduction; nothing to re-hold.
        return 0

    taken, restored = _movements_for_sale(sale)
    if not taken:
        return 0

    from modules.catalog.models import Product

    held = 0
    for product_id, quantity in taken.items():
        if quantity - restored.get(product_id, 0) > 0:
            continue  # still held
        product = Product.objects.select_for_update().get(pk=product_id)
        if not product.track_inventory:
            continue
        if product.stock_level < quantity:
            raise PaymentGatewayError(
                f"Insufficient stock for {product.name}. Available: {product.stock_level}."
            )
        product.stock_level -= quantity
        product.save(update_fields=["stock_level", "updated_at"])
        StockAdjustment.objects.create(
            product=product,
            user=actor,
            quantity=-quantity,
            type=StockAdjustment.AdjustmentType.ADJUST,
            notes=(
                f"{sale_note_prefix(sale)} - M-Pesa pending reservation"
                + (f" ({reason})" if reason else "")
            ),
        )
        record_audit(
            action="stock.reserved",
            entity_type="product",
            entity_id=product.pk,
            actor=actor,
            request=request,
            after={"stock_level": product.stock_level, "sale": sale.sale_number},
        )
        held += quantity

    return held


@transaction.atomic
def void_sale(*, sale, actor, reason: str = "", request=None) -> Sale:
    """Cancel a completed sale and make the money and the shelf agree again.

    A sale that was never paid releases its reservation; a sale that was paid
    is a refund, so every COMPLETED payment is marked ``REFUNDED`` rather than
    deleted — the money movement stays explainable. Payments still in flight
    are failed so a late callback cannot settle a voided sale.

    Voiding an already-voided sale is a no-op that returns the same row: the
    ledger restore below and the status check both make that safe.
    """
    from modules.payments.models import Payment

    sale = Sale.objects.select_for_update().get(pk=sale.pk)
    if sale.status == Sale.Status.VOIDED:
        return sale

    payments = Payment.objects.filter(sale=sale)
    payments.filter(status=Payment.Status.PENDING).update(
        status=Payment.Status.FAILED, updated_at=timezone.now()
    )
    payments.filter(status=Payment.Status.COMPLETED).update(
        status=Payment.Status.REFUNDED, updated_at=timezone.now()
    )

    released = restore_sale_stock(
        sale=sale,
        actor=actor,
        request=request,
        reason="sale voided",
        audit_action="stock.restored",
    )

    sale.status = Sale.Status.VOIDED
    sale.voided_at = timezone.now()
    sale.voided_by = actor
    sale.void_reason = reason[:255]
    sale.save(update_fields=["status", "voided_at", "voided_by", "void_reason"])

    record_audit(
        action="sale.voided",
        entity_type="sale",
        entity_id=sale.pk,
        actor=actor,
        request=request,
        before={"status": Sale.Status.COMPLETED},
        after={
            "status": sale.status,
            "reason": sale.void_reason,
            "stock_restored": released,
            "total_amount": str(sale.total_amount),
        },
    )
    return sale
