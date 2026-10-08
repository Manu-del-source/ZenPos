from decimal import Decimal

from django.conf import settings
from django.db import models

from modules.core.models import BaseModel, SoftDeleteModel

QTY = {"max_digits": 12, "decimal_places": 3}
MONEY = {"max_digits": 14, "decimal_places": 2}


class StockAdjustment(models.Model):
    """A recorded change to a product's stock level.

    Kept as the compatibility record the sales void/restore path still matches
    on (notes prefixed with the sale number). New stock-changing workflows
    write an ``InventoryMovement`` through ``inventory.services.apply_stock_movement``
    and, where a sale restore still needs this row, pass
    ``legacy_adjustment_type``.
    """

    class AdjustmentType(models.TextChoices):
        RESTOCK = "RESTOCK", "Restock/Purchase"
        DAMAGE = "DAMAGE", "Damaged Goods"
        RETURN = "RETURN", "Customer Return"
        ADJUST = "ADJUST", "Manual Adjustment"
        EXPIRE = "EXPIRE", "Expired Goods"

    product = models.ForeignKey(
        "catalog.Product",
        related_name="adjustments",
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
    )
    quantity = models.IntegerField(help_text="Positive adds stock, negative removes it.")
    type = models.CharField(max_length=10, choices=AdjustmentType.choices)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.type} {self.product_id} ({self.quantity})"


class BranchStock(BaseModel):
    """The live on-hand quantity of one product at one branch.

    This is an optimised balance, not the ledger. Every change must go through
    ``apply_stock_movement``, which writes an ``InventoryMovement`` in the same
    transaction. Do not update this row from a view.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="branch_stocks",
        on_delete=models.CASCADE,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        related_name="stock",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "catalog.Product",
        related_name="branch_stocks",
        on_delete=models.CASCADE,
    )
    quantity = models.DecimalField(default=Decimal("0"), **QTY)

    class Meta:
        ordering = ["branch__name", "product__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "product"],
                name="uniq_branch_stock_branch_product",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "product"], name="idx_bstock_org_product"),
        ]

    def __str__(self):
        return f"{self.branch_id}:{self.product_id} = {self.quantity}"


class InventoryMovement(BaseModel):
    """One immutable stock movement.

    There is no update and no delete path. A mistake is a reversing movement.
    ``quantity`` is the signed delta; ``quantity_before`` / ``quantity_after``
    are the branch balance around that delta so a row explains itself without
    replaying the ledger.
    """

    class MovementType(models.TextChoices):
        OPENING_BALANCE = "OPENING_BALANCE", "Opening balance"
        PURCHASE_RECEIPT = "PURCHASE_RECEIPT", "Purchase receipt"
        SALE = "SALE", "Sale"
        RETURN = "RETURN", "Return"
        TRANSFER_OUT = "TRANSFER_OUT", "Transfer out"
        TRANSFER_IN = "TRANSFER_IN", "Transfer in"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"
        DAMAGE = "DAMAGE", "Damage"
        STOCK_COUNT = "STOCK_COUNT", "Stock count"
        OTHER = "OTHER", "Other"

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="inventory_movements",
        on_delete=models.CASCADE,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        related_name="inventory_movements",
        on_delete=models.PROTECT,
    )
    product = models.ForeignKey(
        "catalog.Product",
        related_name="inventory_movements",
        on_delete=models.PROTECT,
    )
    quantity = models.DecimalField(**QTY)
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        db_index=True,
    )
    reference_type = models.CharField(max_length=32, blank=True, default="")
    reference_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="inventory_movements",
        on_delete=models.SET_NULL,
    )
    quantity_before = models.DecimalField(**QTY)
    quantity_after = models.DecimalField(**QTY)
    unit_cost = models.DecimalField(null=True, blank=True, **MONEY)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "created_at"],
                name="idx_imov_org_created",
            ),
            models.Index(
                fields=["branch", "created_at"],
                name="idx_imov_branch_created",
            ),
            models.Index(
                fields=["product", "created_at"],
                name="idx_imov_product_created",
            ),
            models.Index(
                fields=["reference_type", "reference_id"],
                name="idx_imov_reference",
            ),
        ]

    def __str__(self):
        return f"{self.movement_type} {self.product_id} ({self.quantity})"


class StockTransfer(SoftDeleteModel):
    """An inter-branch stock transfer.

    Lifecycle (a state may only be entered from the states listed for it):

        DRAFT -> REQUESTED -> APPROVED -> DISPATCHED -> IN_TRANSIT -> RECEIVED
        DRAFT/REQUESTED/APPROVED -> CANCELLED

    Inventory moves twice, and only then: dispatch decrements the source,
    receipt increments the destination. Both write ledger rows. A transfer
    never changes catalogue identity — only where the units sit.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        REQUESTED = "REQUESTED", "Requested"
        APPROVED = "APPROVED", "Approved"
        DISPATCHED = "DISPATCHED", "Dispatched"
        IN_TRANSIT = "IN_TRANSIT", "In transit"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    ALLOWED_TRANSITIONS = {
        Status.DRAFT: {Status.REQUESTED, Status.CANCELLED},
        Status.REQUESTED: {Status.APPROVED, Status.DRAFT, Status.CANCELLED},
        Status.APPROVED: {Status.DISPATCHED, Status.CANCELLED},
        Status.DISPATCHED: {Status.IN_TRANSIT, Status.RECEIVED},
        Status.IN_TRANSIT: {Status.RECEIVED},
        Status.RECEIVED: set(),
        Status.CANCELLED: set(),
    }

    EDITABLE_STATUSES = {Status.DRAFT}

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="stock_transfers",
        on_delete=models.CASCADE,
    )
    source_branch = models.ForeignKey(
        "branches.Branch",
        related_name="transfers_out",
        on_delete=models.PROTECT,
    )
    destination_branch = models.ForeignKey(
        "branches.Branch",
        related_name="transfers_in",
        on_delete=models.PROTECT,
    )
    number = models.CharField(max_length=32, db_index=True)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    notes = models.TextField(blank=True, default="")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="transfers_requested",
        on_delete=models.SET_NULL,
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="transfers_approved",
        on_delete=models.SET_NULL,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="transfers_dispatched",
        on_delete=models.SET_NULL,
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="transfers_received",
        on_delete=models.SET_NULL,
    )
    received_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "number"],
                name="uniq_transfer_org_number",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="idx_trf_org_status"),
            models.Index(fields=["source_branch", "status"], name="idx_trf_src_status"),
            models.Index(
                fields=["destination_branch", "status"],
                name="idx_trf_dst_status",
            ),
        ]

    def __str__(self):
        return self.number

    def can_transition_to(self, new_status) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS[self.status]

    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES


class StockTransferLine(BaseModel):
    """One product on a stock transfer."""

    transfer = models.ForeignKey(
        StockTransfer,
        related_name="lines",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "catalog.Product",
        related_name="transfer_lines",
        on_delete=models.PROTECT,
    )
    requested_quantity = models.DecimalField(
        **QTY,
    )
    approved_quantity = models.DecimalField(default=Decimal("0"), **QTY)
    dispatched_quantity = models.DecimalField(default=Decimal("0"), **QTY)
    received_quantity = models.DecimalField(default=Decimal("0"), **QTY)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["transfer", "product"],
                name="uniq_transfer_line_product",
            ),
        ]

    def __str__(self):
        return f"{self.transfer_id}: {self.product_id} x {self.requested_quantity}"
