from django.conf import settings
from django.db import models

from modules.core.models import BaseModel


class LoyaltyRule(BaseModel):
    """How this organization awards points.

    One rule per tenant for now: 1 point per ``amount`` KES of completed sales.
    """

    organization = models.OneToOneField(
        "organizations.Organization",
        related_name="loyalty_rule",
        on_delete=models.CASCADE,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=100,
        help_text="KES per point. 100 means 1 point per KES 100.",
    )
    points = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "loyalty rule"

    def __str__(self):
        return f"{self.points} pt / {self.amount} {self.organization_id}"


class LoyaltyAccount(BaseModel):
    """A customer's points account. Balance is maintained transactionally."""

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="loyalty_accounts",
        on_delete=models.CASCADE,
    )
    customer = models.OneToOneField(
        "customers.Customer",
        related_name="loyalty_account",
        on_delete=models.CASCADE,
    )
    points_balance = models.IntegerField(default=0)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.customer_id}: {self.points_balance}"


class LoyaltyLedger(BaseModel):
    """One immutable points movement."""

    class Action(models.TextChoices):
        EARN = "EARN", "Earn"
        REDEEM = "REDEEM", "Redeem"
        ADJUST = "ADJUST", "Adjust"
        REVERSAL = "REVERSAL", "Reversal"
        EXPIRE = "EXPIRE", "Expire"

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="loyalty_ledger",
        on_delete=models.CASCADE,
    )
    account = models.ForeignKey(
        LoyaltyAccount,
        related_name="entries",
        on_delete=models.CASCADE,
    )
    customer = models.ForeignKey(
        "customers.Customer",
        related_name="loyalty_entries",
        on_delete=models.CASCADE,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        related_name="loyalty_entries",
        on_delete=models.SET_NULL,
    )
    points = models.IntegerField(help_text="Signed. Positive credits the account.")
    action = models.CharField(max_length=12, choices=Action.choices, db_index=True)
    reference_type = models.CharField(max_length=32, blank=True, default="")
    reference_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="loyalty_entries",
        on_delete=models.SET_NULL,
    )
    notes = models.TextField(blank=True, default="")
    balance_after = models.IntegerField()

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "loyalty ledger"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "action", "reference_type", "reference_id"],
                condition=~models.Q(reference_id=""),
                name="uniq_loyalty_org_action_ref",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "created_at"], name="idx_loyal_cust_created"),
        ]

    def __str__(self):
        return f"{self.action} {self.points} ({self.customer_id})"
