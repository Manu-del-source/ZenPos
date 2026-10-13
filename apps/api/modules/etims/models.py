from django.db import models

from modules.core.models import BaseModel
from modules.organizations.models import Organization
from modules.sales.models import Sale


class EtimsDevice(BaseModel):
    """An Electronic Receipting System (ERS) device for one organization.

    eTIMS invoices are issued by registered devices, and registration is a
    KRA-side act. The identifiers KRA assigns (device number, API key) stay
    empty until a human has confirmed the registration with the authority —
    nothing in this system invents them (ADR-0019).
    """

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="etims_devices",
    )
    name = models.CharField(max_length=128)
    # The organization's KRA PIN as registered for eTIMS.
    kda_pin = models.CharField(max_length=32)
    device_number = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="Assigned by KRA at device registration. Empty until confirmed.",
    )
    api_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Assigned by KRA. A credential: redacted from stored "
        "payloads by any transmitting adapter, never shown in admin.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"], name="uniq_etims_device_org_name"
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.organization.name})"


class EtimsInvoice(BaseModel):
    """The eTIMS document for one sale.

    An invoice is a *document*, not a payment: it snapshots what the sale
    was at the moment of issue (lines, per-rate tax, totals) and its
    lifecycle is ISSUED -> CANCELLED, mirroring the sale's void. Rows are
    never deleted and their snapshots never rewritten (ADR-0013/0015: the
    history stays explainable).

    ``uin`` is the Unique Invoice Number assigned by the KRA system. This
    system never generates one: a verified transmission adapter writes it
    onto the row, and until that adapter exists the field is blank by
    design (ADR-0019).
    """

    class Status(models.TextChoices):
        ISSUED = "ISSUED", "Issued"
        CANCELLED = "CANCELLED", "Cancelled"

    # PROTECT: an invoice that outlived its sale would be an unexplainable
    # document, and the sale itself is protected the other way by its own
    # ledger.
    sale = models.ForeignKey(
        Sale,
        on_delete=models.PROTECT,
        related_name="etims_invoices",
    )
    device = models.ForeignKey(
        EtimsDevice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ISSUED,
        db_index=True,
    )
    uin = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="KRA-assigned. Blank until a verified adapter transmits.",
    )
    # Set explicitly, not auto: a backfilled invoice carries the time it
    # represents, not the time it was keyed in.
    issued_at = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    # The document, from persisted rows only. Money values are strings:
    # JSONField stores no Decimal, and the string form is what the receipt
    # and any transmission payload print.
    line_items = models.JSONField()
    tax_breakdown = models.JSONField()
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")

    class Meta:
        ordering = ["-issued_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["sale"], name="uniq_etims_invoice_sale"),
        ]

    def __str__(self):
        return f"eTIMS invoice for {self.sale.sale_number} ({self.status})"
