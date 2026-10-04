from django.conf import settings
from django.db import models


class StockAdjustment(models.Model):
    """A recorded change to a product's stock level.

    This is the seed of the append-only inventory ledger that phase 5 builds
    out. Stock must never change without a row here explaining why.
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
