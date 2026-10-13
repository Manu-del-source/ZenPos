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
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.catalog.models import Product
from modules.core.audit import record_audit

from .models import BranchStock, InventoryMovement, StockAdjustment, StockCount, StockCountLine

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


def _next_count_number(organization) -> str:
    last = (
        StockCount.objects.filter(organization=organization)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )
    if last is None or not last.startswith("SC-"):
        return "SC-000001"
    return f"SC-{int(last[3:]) + 1:06d}"


def post_stock_count(
    *,
    organization,
    branch,
    counts,
    actor=None,
    request=None,
    notes: str = "",
) -> StockCount:
    """Post a physical stock count at one branch.

    ``counts`` is an iterable of ``(product, counted_quantity)``. Each
    product's variance against the branch book is posted as a
    ``STOCK_COUNT`` movement; a zero variance still records its line,
    because the count happening is itself a fact even when the shelf
    agreed with the books.

    The products are locked in primary-key order before any movement is
    written: two concurrent counts of the same branch may take the same
    shelf in different orders, and a fixed lock order is what keeps that
    from deadlocking. While the product lock is held, no other workflow can
    move that product's stock, so the book quantity snapshotted on the line
    is exactly the balance the correcting movement adjusts.
    """
    pairs = sorted(
        ((product, _as_decimal(counted)) for product, counted in counts),
        key=lambda p: p[0].pk,
    )
    for _product, counted in pairs:
        if counted < 0:
            raise ValidationError({"counts": "A counted quantity cannot be negative."})

    with transaction.atomic():
        count = StockCount.objects.create(
            organization=organization,
            branch=branch,
            number=_next_count_number(organization),
            counted_at=timezone.now(),
            counted_by=actor if getattr(actor, "is_authenticated", False) else None,
            notes=notes or "",
        )
        corrected = 0
        for product, counted in pairs:
            product = Product.objects.select_for_update().get(pk=product.pk)
            book = branch_on_hand(product, branch)
            variance = counted - book
            if variance != 0:
                apply_stock_movement(
                    product=product,
                    quantity=variance,
                    movement_type=InventoryMovement.MovementType.STOCK_COUNT,
                    organization=organization,
                    branch=branch,
                    reference_type="stock_count",
                    reference_id=count.pk,
                    actor=actor,
                    notes=(
                        f"Stock count {count.number} at {branch.name}: "
                        f"counted {counted}, book {book}"
                    ),
                    request=request,
                )
                corrected += 1
            StockCountLine.objects.create(
                stock_count=count,
                product=product,
                book_quantity=book,
                counted_quantity=counted,
                variance=variance,
            )

        record_audit(
            action="inventory.stock_counted",
            entity_type="stock_count",
            entity_id=count.pk,
            actor=actor,
            request=request,
            branch=branch,
            after={
                "number": count.number,
                "branch": branch.name,
                "lines": len(pairs),
                "corrected": corrected,
            },
        )
    return count


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
