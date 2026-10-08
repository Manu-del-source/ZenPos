from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from modules.core.models import BaseModel, SoftDeleteModel

MONEY = {"max_digits": 14, "decimal_places": 2}


class Supplier(SoftDeleteModel):
    """A business the organization buys stock from.

    Suppliers belong to the organization, not to a branch: the same supplier
    delivers to every shop. Branch relevance arrives with the purchase order,
    which names the branch it is for.

    ``status`` is an operational flag, not a lifecycle: ACTIVE means the
    supplier may be written on a purchase order today, BLOCKED means existing
    orders keep their history but no new business should be placed. Closing a
    relationship is an archive (``deleted_at``), which hides the supplier from
    the directory while keeping every purchase order they ever filled
    explainable — the same convention ``Product`` uses.

    The archive also frees the name: the unique constraint below only binds
    live rows, so a business can archive a supplier and re-add the same trading
    name later without operator intervention.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        BLOCKED = "BLOCKED", "Blocked"

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="suppliers",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="", db_index=True)
    email = models.EmailField(blank=True, default="")
    address = models.TextField(blank=True, default="")
    payment_terms = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="e.g. Net 30, COD, 2/10 Net 30. Free text: terms are agreed, not configured.",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["name"]
        constraints = [
            # Two suppliers with the same trading name in one organization is a
            # data-entry accident, not a choice. Archived rows are exempt so a
            # name can be reused after an archive.
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_supplier_org_name",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="idx_supplier_org_status",
            ),
        ]

    def __str__(self):
        return self.name


class PurchaseOrder(SoftDeleteModel):
    """A reorder raised against one supplier, for one branch.

    The order is the paper trail behind the stock: what was asked for, at what
    cost, and — once the GRN slice lands — what the branch actually received.
    Until then the lifecycle stops at receipt-signoff states that receiving
    will drive.

    Lifecycle (a state may only be entered from the states listed for it):

        DRAFT -> SUBMITTED -> APPROVED -> PARTIALLY_RECEIVED -> RECEIVED
        DRAFT/SUBMITTED/APPROVED -> CANCELLED

    Enforcement lives in :attr:`ALLOWED_TRANSITIONS`; the viewsets consult it
    so no endpoint can skip a step (a DRAFT cannot appear in the approved
    list, a RECEIVED order cannot be un-cancelled into an editable one).
    Editing is DRAFT-only: once an order is submitted it represents something
    that was said to a supplier, not a draft of it.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        APPROVED = "APPROVED", "Approved"
        PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED", "Partially received"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    DRAFT = Status.DRAFT  # the common comparison in views and serializers

    #: status -> the statuses it may move to. SUBMITTED -> DRAFT is reject:
    #: the approver sends a draft back for rework instead of killing it.
    ALLOWED_TRANSITIONS = {
        Status.DRAFT: {Status.SUBMITTED, Status.CANCELLED},
        Status.SUBMITTED: {Status.APPROVED, Status.DRAFT, Status.CANCELLED},
        Status.APPROVED: {Status.PARTIALLY_RECEIVED, Status.RECEIVED, Status.CANCELLED},
        Status.PARTIALLY_RECEIVED: {Status.RECEIVED},
        Status.RECEIVED: set(),
        Status.CANCELLED: set(),
    }

    #: statuses from which the header/lines may be edited
    EDITABLE_STATUSES = {Status.DRAFT}

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="purchase_orders",
        on_delete=models.CASCADE,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        related_name="purchase_orders",
        on_delete=models.PROTECT,
        help_text="The branch the goods are delivered to.",
    )
    supplier = models.ForeignKey(
        Supplier,
        related_name="purchase_orders",
        on_delete=models.PROTECT,
    )
    number = models.CharField(max_length=32, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    expected_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        related_name="purchase_orders_raised",
        on_delete=models.SET_NULL,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="purchase_orders_approved",
        on_delete=models.SET_NULL,
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # One number per tenant; the sequence is generated, not typed, and
            # it survives an archive (numbers are never reused).
            models.UniqueConstraint(
                fields=["organization", "number"],
                name="uniq_po_org_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="idx_po_org_status",
            ),
            models.Index(
                fields=["branch", "status"],
                name="idx_po_branch_status",
            ),
        ]

    def __str__(self):
        return self.number

    def can_transition_to(self, new_status) -> bool:
        return new_status in self.ALLOWED_TRANSITIONS[self.status]

    def is_editable(self) -> bool:
        return self.status in self.EDITABLE_STATUSES

    @property
    def total_cost(self):
        """Order total in memory; the serializer aggregates it in the database."""
        return sum(
            (line.quantity * line.unit_cost for line in self.lines.all()),
            start=Decimal("0"),
        )


class PurchaseOrderLine(BaseModel):
    """One product on a purchase order, at the agreed cost.

    ``quantity`` is what was ordered. What arrived arrives in slice 3 as
    goods-received lines, which reference this line — so a received order
    still knows which ask it satisfies.
    """

    purchase_order = models.ForeignKey(
        PurchaseOrder,
        related_name="lines",
        on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "catalog.Product",
        related_name="purchase_order_lines",
        on_delete=models.PROTECT,
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        validators=[MinValueValidator(Decimal("0.001"))],
        help_text="Ordered quantity. Decimals for weighed goods sold by the kg/litre.",
    )
    unit_cost = models.DecimalField(
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Cost per unit the supplier agreed. Defaults to the product's cost price.",
        **MONEY,
    )

    class Meta:
        ordering = ["purchase_order__created_at", "id"]
        constraints = [
            # The same product twice on one order is a typo, not two asks.
            models.UniqueConstraint(
                fields=["purchase_order", "product"],
                name="uniq_po_line_order_product",
            ),
        ]

    def __str__(self):
        return f"{self.purchase_order_id}: {self.product_id} x {self.quantity}"
