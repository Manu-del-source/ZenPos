from django.conf import settings
from django.db import models


class Sale(models.Model):
    """A completed sale.

    Phase 6 adds branch, till, cash session and line-level pricing columns, and
    moves payment details off this table into a ``payments`` table so split and
    partial payments become possible. Money columns are computed by the server
    from the catalogue at sale time; phase 5 stopped accepting them from the
    request body.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "CASH", "Cash"
        MPESA = "MPESA", "M-Pesa"
        SPLIT = "SPLIT", "Split Payment"

    sale_number = models.CharField(max_length=50, unique=True, db_index=True)
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

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
