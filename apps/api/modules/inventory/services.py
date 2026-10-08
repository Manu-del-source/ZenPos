"""The single writer of stock.

Every change to on-hand quantity goes through ``apply_stock_movement``. The
movement row is the explanation; ``BranchStock`` is the current balance at a
branch; ``Product.stock_level`` is kept in step so the existing POS path still
reads a number it understands.

Callers must already be inside ``transaction.atomic()``. This function locks
the product (and the branch balance when a branch is named) so two cashiers
cannot both sell the last unit.
"""

from decimal import Decimal

from django.db import transaction
from rest_framework.exceptions import ValidationError

from modules.catalog.models import Product
from modules.core.audit import record_audit

from .models import BranchStock, InventoryMovement, StockAdjustment

ADJUSTMENT_TO_MOVEMENT = {
    StockAdjustment.AdjustmentType.RESTOCK: InventoryMovement.MovementType.PURCHASE_RECEIPT,
    StockAdjustment.AdjustmentType.DAMAGE: InventoryMovement.MovementType.DAMAGE,
    StockAdjustment.AdjustmentType.RETURN: InventoryMovement.MovementType.RETURN,
    StockAdjustment.AdjustmentType.ADJUST: InventoryMovement.MovementType.ADJUSTMENT,
    StockAdjustment.AdjustmentType.EXPIRE: InventoryMovement.MovementType.OTHER,
}


def _as_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@transaction.atomic
def apply_stock_movement(
    *,
    product,
    quantity,
    movement_type,
    organization=None,
    branch=None,
    reference_type: str = "",
    reference_id: str = "",
    actor=None,
    unit_cost=None,
    notes: str = "",
    allow_negative: bool = False,
    legacy_adjustment_type=None,
    request=None,
) -> InventoryMovement:
    """Apply a signed quantity change and write the ledger row.

    ``quantity`` is the delta: positive adds stock, negative removes it.
    ``allow_negative`` is for corrections that must be able to drive a balance
    below zero; sales, receipts and transfers leave it false.
    """
    quantity = _as_decimal(quantity)
    if quantity == 0:
        raise ValidationError({"quantity": "Quantity change cannot be zero."})

    product = Product.objects.select_for_update().get(pk=product.pk)
    organization = organization or product.organization

    if branch is not None:
        # Seed the first branch balance from the catalogue column so stock
        # that predates per-branch inventory remains sellable. Later branches
        # start at zero and must be filled by receiving or transfer.
        initial = Decimal("0")
        if not BranchStock.objects.filter(product=product).exists():
            initial = Decimal(product.stock_level)
        stock, _created = BranchStock.objects.get_or_create(
            organization=organization,
            branch=branch,
            product=product,
            defaults={"quantity": initial},
        )
        stock = BranchStock.objects.select_for_update().get(pk=stock.pk)
        before = stock.quantity
        after = before + quantity
        if after < 0 and not allow_negative:
            raise ValidationError(
                f"Insufficient stock for {product.name} at {branch.name}. "
                f"Available: {before}."
            )
        stock.quantity = after
        stock.save(update_fields=["quantity", "updated_at"])
    else:
        before = Decimal(product.stock_level)
        after = before + quantity
        if after < 0 and not allow_negative:
            raise ValidationError(
                f"Insufficient stock for {product.name}. Available: {before}."
            )

    # Catalogue column stays in step for the POS and for reports that still
    # read it. Truncation toward zero matches the integer column.
    product.stock_level = int(Decimal(product.stock_level) + quantity)
    product.save(update_fields=["stock_level", "updated_at"])

    movement = InventoryMovement.objects.create(
        organization=organization,
        branch=branch,
        product=product,
        quantity=quantity,
        movement_type=movement_type,
        reference_type=reference_type or "",
        reference_id=str(reference_id) if reference_id else "",
        actor=actor,
        quantity_before=before,
        quantity_after=after,
        unit_cost=unit_cost,
        notes=notes or "",
    )

    if legacy_adjustment_type is not None:
        StockAdjustment.objects.create(
            product=product,
            user=actor,
            quantity=int(quantity),
            type=legacy_adjustment_type,
            notes=notes or "",
        )

    record_audit(
        action="inventory.moved",
        entity_type="inventory_movement",
        entity_id=movement.pk,
        actor=actor,
        request=request,
        branch=branch,
        after={
            "product": str(product.pk),
            "movement_type": movement_type,
            "quantity": str(quantity),
            "quantity_before": str(before),
            "quantity_after": str(after),
            "reference_type": reference_type or "",
            "reference_id": str(reference_id) if reference_id else "",
        },
    )
    return movement


def branch_on_hand(product, branch) -> Decimal:
    """Current branch balance, or zero when the product has never moved there."""
    if branch is None:
        return Decimal(product.stock_level)
    row = BranchStock.objects.filter(branch=branch, product=product).first()
    return row.quantity if row is not None else Decimal("0")


def available_for_sale(product, branch=None) -> Decimal:
    """Units the till may sell.

    Prefer the branch balance when one exists for this product at this branch.
    Otherwise fall back to the catalogue column so stock that predates
    per-branch inventory is still sellable at the first till that asks.
    """
    if not product.track_inventory:
        return Decimal("Infinity")
    if branch is not None:
        row = BranchStock.objects.filter(branch=branch, product=product).first()
        if row is not None:
            return row.quantity
    return Decimal(product.stock_level)
