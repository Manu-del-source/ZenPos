from django.db import models
from django.utils import timezone

from modules.core.managers import AllObjectsManager, SoftDeleteManager


class Customer(models.Model):
    """A retail customer.

    Organization-scoped: a customer list is a phone book of real people, and
    one shop's staff must not be able to read another shop's. Phones are
    unique *within* an organization rather than globally, because the same
    person may shop at two different businesses — which the pre-phase-4
    global unique constraint made impossible.

    The points balance is not a column here. It lives on the loyalty
    account, maintained transactionally by the loyalty ledger, so every
    point a customer has is explainable (ADR-0021). The customer row keeps
    its integer key for now: re-keying to UUIDs rewrites ``Sale`` and the
    customer API shape, which pays off only with the multi-tenant phase's
    offline identity work, not before.

    A customer is archived (``deleted_at``), never deleted: the directory
    hides them and their phone can be reused, but every sale they ever made
    keeps pointing at the row that explains it.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="customers",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=15, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        ordering = ["name"]
        constraints = [
            # Archived rows are exempt, like the supplier directory: closing a
            # relationship frees the number for the next holder.
            models.UniqueConstraint(
                fields=["organization", "phone"],
                condition=models.Q(deleted_at__isnull=True),
                name="uniq_customer_org_phone",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    @property
    def points_balance(self):
        """The customer's loyalty balance, from the account the ledger owns.

        A customer without a loyalty account has never earned, redeemed or
        been adjusted: zero. (The reverse one-to-one raises rather than
        returning ``None``, so the check is a ``hasattr``, not an ``_id``.)
        """
        if self.pk is None or not hasattr(self, "loyalty_account"):
            return 0
        return self.loyalty_account.points_balance

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])
