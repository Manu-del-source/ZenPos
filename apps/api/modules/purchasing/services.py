"""The cost basis: what the catalogue cost column says after a receipt.

Sale lines snapshot ``Product.cost_price`` at sale time, and the P&L's cost
of goods sold sums those snapshots. Until the cost column reflects what was
actually paid for the latest units, both describe the cost the shop *thinks*
it has, not the cost it *has*. When a goods received note posts, the cost
column moves to the weighted average of the stock on hand and the receipt.

History is untouched by design: the GRN lines keep the real receipt costs,
the ledger keeps per-movement costs, and only *future* sale snapshots see the
new basis.
"""

from decimal import ROUND_HALF_UP, Decimal

from modules.core.audit import record_audit

TWO_PLACES = Decimal("0.01")


def receipt_cost(
    *, on_hand: Decimal, old_cost: Decimal, received_quantity: Decimal, unit_cost: Decimal
) -> Decimal:
    """The weighted-average cost after receiving ``received_quantity`` at ``unit_cost``.

    With nothing on hand the receipt defines the basis outright; averaging
    a stale cost column against zero stock would be inventing a blend.
    """
    if on_hand <= 0:
        return unit_cost.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    total_cost = on_hand * old_cost + received_quantity * unit_cost
    return (total_cost / (on_hand + received_quantity)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def update_product_cost_from_receipt(
    *,
    product,
    on_hand: Decimal,
    received_quantity: Decimal,
    unit_cost: Decimal,
    grn,
    order,
    actor=None,
    request=None,
) -> Decimal:
    """Move the catalogue cost column to the post-receipt weighted average.

    Called inside the GRN post transaction, with the product row already
    locked by the caller — no other receipt can interleave for this product.
    ``on_hand`` is the stock *before* this receipt.

    Two no-ops are deliberate: a zero-cost receipt (a donation, a free
    sample) moves stock but defines no price to average, and a receipt at
    exactly the current cost would otherwise churn the column and the audit
    log about nothing.

    Returns the cost in force afterwards (which may be the previous one).
    """
    if unit_cost is None or unit_cost <= 0:
        return product.cost_price

    new_cost = receipt_cost(
        on_hand=on_hand,
        old_cost=product.cost_price,
        received_quantity=received_quantity,
        unit_cost=unit_cost,
    )
    if new_cost == product.cost_price:
        return new_cost

    old_cost = product.cost_price
    product.cost_price = new_cost
    product.save(update_fields=["cost_price", "updated_at"])
    record_audit(
        action="product.cost_updated",
        entity_type="product",
        entity_id=product.pk,
        actor=actor,
        request=request,
        before={"cost_price": str(old_cost)},
        after={
            "cost_price": str(new_cost),
            "reason": f"GRN {grn.number} against {order.number}",
        },
    )
    return new_cost
