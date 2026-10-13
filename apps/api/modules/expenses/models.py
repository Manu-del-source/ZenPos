from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from modules.core.models import BaseModel

MONEY = {"max_digits": 14, "decimal_places": 2}


class ExpenseCategory(BaseModel):
    """A named cost bucket that expenses post into.

    Categories are per organization on purpose: each tenant shapes its own
    chart of costs, and a shared global list would leak one shop's accounting
    habits to every other tenant.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="expense_categories",
        on_delete=models.PROTECT,
    )
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Inactive categories can no longer receive new expenses; "
            "existing expenses keep pointing at them."
        ),
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_expense_category_org_name",
            )
        ]

    def __str__(self):
        return self.name


class Expense(BaseModel):
    """One money-out event. Append-only: corrected by reversal, never edited.

    Financial records in this codebase are append-only and corrected by
    reversal (ADR-0014 for cash, ADR-0015 here): there is no update or delete
    endpoint for an expense, and a mistake is fixed by a *reversal* row that
    references the original. Reports therefore treat a reversal as negative.
    The full history of any figure stays readable in place.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="expenses",
        on_delete=models.PROTECT,
        help_text="Denormalised from the branch; the tenant boundary for this row.",
    )
    branch = models.ForeignKey(
        "branches.Branch",
        related_name="expenses",
        on_delete=models.PROTECT,
        help_text="Where the money went out. Head-office costs post to the paying branch.",
    )
    category = models.ForeignKey(
        ExpenseCategory,
        related_name="expenses",
        on_delete=models.PROTECT,
    )
    expense_number = models.CharField(max_length=50, unique=True, db_index=True)
    date = models.DateField(
        help_text=(
            "When the expense was incurred, not when it was recorded: "
            "this is the period it reports against."
        )
    )
    amount = models.DecimalField(
        **MONEY,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=(
            "Always positive. A correction is a separate reversal row, "
            "which reports count as negative."
        ),
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Receipt or invoice number, for the paper trail.",
    )
    notes = models.CharField(max_length=500, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="expenses_created",
        on_delete=models.PROTECT,
    )
    reversal_of = models.ForeignKey(
        "self",
        related_name="reversals",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text="Set on a reversal row; null on a genuine expense.",
    )

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["organization", "date"], name="idx_expense_org_date"),
            models.Index(fields=["branch", "date"], name="idx_expense_branch_date"),
        ]

    @property
    def is_reversal(self):
        return self.reversal_of is not None

    def __str__(self):
        return self.expense_number
