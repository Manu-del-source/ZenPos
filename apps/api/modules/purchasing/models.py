from django.db import models

from modules.core.models import SoftDeleteModel


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
