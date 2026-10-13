from decimal import Decimal

from django.conf import settings
from django.db import models

from modules.core.models import BaseModel


class Branch(BaseModel):
    """A physical shop belonging to an organization.

    Branches are first-class: stock, tills, cash sessions, sales and reports all
    hang off a branch, and staff access is granted per branch.

    ``code`` is unique within the organization rather than globally, so two
    organizations can both run a branch called "BR-001".
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="branches",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=32)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    timezone = models.CharField(max_length=64, default="Africa/Nairobi")
    manager = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        related_name="managed_branches",
        on_delete=models.SET_NULL,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["organization__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                name="uniq_branch_org_code",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

class Till(BaseModel):
    """A physical cash register that belongs to one branch.

    Tills are where cashiers work: a cash session opens at a till, sales are
    attributed to it, and the shift's drawer is reconciled against it. Like
    branches, a till is deactivated (``is_active``) rather than deleted —
    closed sessions and their movements would otherwise lose the register they
    happened at.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="tills",
        on_delete=models.PROTECT,
        help_text="Denormalised from the branch so tenant scoping does not join.",
    )
    branch = models.ForeignKey(
        Branch,
        related_name="tills",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["branch__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "name"],
                name="uniq_till_branch_name",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.branch.code})"


class CashSession(BaseModel):
    """One cashier's shift at one till, from opening float to counted close.

    The drawer only changes through ``CashMovement`` rows and the cash sales
    and cash refunds attributed to the session; nothing else may move cash in
    or out of it. That is what makes ``expected_cash`` explainable: it is the
    opening float plus every recorded cash movement, and the close compares it
    with the physical count.

    A session is OPEN until closed exactly once. The partial unique constraint
    guarantees at most one OPEN session per till at the database level, so two
    cashiers cannot race the same register even if the application check is
    bypassed.
    """

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    till = models.ForeignKey(
        Till,
        related_name="sessions",
        on_delete=models.PROTECT,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="cash_sessions",
        on_delete=models.PROTECT,
        help_text="Denormalised from the till so tenant scoping does not join.",
    )
    branch = models.ForeignKey(
        Branch,
        related_name="cash_sessions",
        on_delete=models.PROTECT,
        help_text="Denormalised from the till so branch scoping does not join.",
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="opened_cash_sessions",
        on_delete=models.PROTECT,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    opening_cash = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    # Written at close, by the server, from the recorded movements only. The
    # client supplies the physical count; the expected figure is never client
    # data.
    counted_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    expected_cash = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    # counted - expected. Negative means short, positive means over.
    cash_variance = models.DecimalField(max_digits=14, decimal_places=2, null=True)
    close_notes = models.CharField(max_length=255, blank=True, default="")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="closed_cash_sessions",
        on_delete=models.PROTECT,
    )
    # Supervisor review of a closed session's discrepancy. Review is a
    # deliberate, audited annotation on a closed record — the numbers above
    # are never rewritten.
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="reviewed_cash_sessions",
        on_delete=models.PROTECT,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # A literal value, not Status.OPEN: the nested choices class is
            # not yet bound in the class body while Meta is evaluated.
            models.UniqueConstraint(
                fields=["till_id"],
                condition=models.Q(status="OPEN"),
                name="uniq_one_open_session_per_till",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status"], name="idx_session_org_status"),
            models.Index(fields=["branch", "created_at"], name="idx_session_branch_created"),
            models.Index(fields=["opened_by", "status"], name="idx_session_opener_status"),
        ]

    def __str__(self):
        return f"Cash session {self.pk} at {self.till} ({self.status})"


class CashMovement(BaseModel):
    """One movement of cash into or out of a session's drawer.

    Append-only: the API has no update or delete path, and corrections are
    recorded as further movements (a reversal is a CASH_OUT with the reason
    saying so). ``amount`` is always positive; ``movement_type`` carries the
    direction, and ``source`` records which business event produced the row so
    reconciliation can split manual handling from sales and refunds.
    """

    class Type(models.TextChoices):
        CASH_IN = "CASH_IN", "Cash in"
        CASH_OUT = "CASH_OUT", "Cash out"
        CASH_DROP = "CASH_DROP", "Cash drop"

    class Source(models.TextChoices):
        MANUAL = "MANUAL", "Manual movement"
        SALE = "SALE", "Cash sale"
        REFUND = "REFUND", "Cash refund"

    session = models.ForeignKey(
        CashSession,
        related_name="movements",
        on_delete=models.PROTECT,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="cash_movements",
        on_delete=models.PROTECT,
        help_text="Denormalised from the session so tenant scoping does not join.",
    )
    branch = models.ForeignKey(
        Branch,
        related_name="cash_movements",
        on_delete=models.PROTECT,
        help_text="Denormalised from the session so branch scoping does not join.",
    )
    movement_type = models.CharField(max_length=10, choices=Type.choices, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.MANUAL)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(
        max_length=255,
        help_text="Required: who authorised this and why. Cash handling must be explainable.",
    )
    reference = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Optional voucher, receipt or sale number the movement evidences.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="cash_movements",
        on_delete=models.PROTECT,
    )

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["session", "movement_type"], name="idx_movement_session_type"),
        ]

    @property
    def signed_amount(self) -> Decimal:
        """The effect on the drawer: in is positive, out and drops are negative."""
        if self.movement_type == self.Type.CASH_IN:
            return self.amount
        return -self.amount

    def __str__(self):
        return f"{self.movement_type} {self.amount} ({self.source}) at {self.session}"
