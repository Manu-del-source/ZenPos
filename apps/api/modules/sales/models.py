from django.conf import settings
from django.db import models


class Sale(models.Model):
    """A completed sale.

    Money columns are computed by the server from the catalogue at sale time;
    the request body can only disagree with them, never set them.

    ``branch`` and ``organization`` are denormalised onto the sale so branch
    scoping and branch reporting do not have to join through the cashier on
    every query. ``organization`` is nullable only for rows written before
    multi-tenancy reached this table; every sale created through the API has
    one.

    ``client_reference`` is the POS-supplied idempotency key. A cashier whose
    connection drops mid-checkout retries with the same reference, and the
    unique ``(organization, client_reference)`` constraint — not a frontend
    guard — is what stops the retry from becoming a second sale with a second
    stock movement.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        MPESA = "MPESA", "M-Pesa"
        SPLIT = "SPLIT", "Split Payment"

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        VOIDED = "VOIDED", "Voided"

    sale_number = models.CharField(max_length=50, unique=True, db_index=True)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        related_name="sales",
        on_delete=models.PROTECT,
        help_text="Denormalised from the cashier; the tenant boundary for this row.",
    )
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        related_name="sales",
        on_delete=models.PROTECT,
        help_text="Where the sale was rung up. Null only for pre-branch rows.",
    )
    client_reference = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
        help_text="POS idempotency key: repeating it returns the first sale.",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=10, choices=PaymentMethod.choices)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.COMPLETED,
        db_index=True,
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="sales_voided",
        on_delete=models.PROTECT,
    )
    void_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # Postgres treats empty strings as ordinary values, so the partial
            # condition keeps legacy rows (no reference) from colliding.
            models.UniqueConstraint(
                fields=["organization", "client_reference"],
                condition=~models.Q(client_reference=""),
                name="uniq_sale_org_client_ref",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="idx_sale_org_created"),
            models.Index(fields=["branch", "created_at"], name="idx_sale_branch_created"),
        ]

    def __str__(self):
        return self.sale_number


class SaleItem(models.Model):
    """One line of a sale, with the money resolved at sale time.

    Every monetary column is written by the server from the product and its tax
    configuration — see ``compute_line_money`` in serializers.py. They are
    captured per line, not read from the product later, so a price or tax
    change never rewrites history.
    """

    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT)
    quantity = models.IntegerField()
    # The listed unit price at sale time, resolved from the product.
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    # Landed cost at sale time. Historical margin needs this once the product's
    # cost changes. Null only for rows written before phase 5.
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )
    # Net (pre-tax) line amount. For an inclusive tax this is less than
    # ``unit_price * quantity``; the customer pays ``subtotal + tax_amount``.
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # A snapshot of the tax band applied, so a receipt can group tax per rate
    # without joining back through the product (whose rate may since have
    # changed) and so the eTIMS adapter has what it needs.
    tax_rate_name = models.CharField(max_length=64, blank=True, default="")
    tax_rate_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.quantity} x {self.product_id}"
