from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from modules.core.models import BaseModel, SoftDeleteModel

MONEY = {"max_digits": 14, "decimal_places": 2}


class Category(BaseModel):
    """A product category, optionally nested (Groceries > Dairy > Milk)."""

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="categories",
        on_delete=models.CASCADE,
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        related_name="children",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "parent", "name"],
                name="uniq_category_org_parent_name",
            ),
            # NULLs are distinct in Postgres, so the constraint above does not
            # cover top-level categories. This one does.
            models.UniqueConstraint(
                fields=["organization", "name"],
                condition=models.Q(parent__isnull=True),
                name="uniq_root_category_org_name",
            ),
        ]

    def __str__(self):
        return self.name


class Brand(BaseModel):
    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="brands",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_brand_org_name",
            ),
        ]

    def __str__(self):
        return self.name


class Unit(BaseModel):
    """A unit of measure: Piece, Kilogram, Litre, Pack of 6."""

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="units",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=64)
    abbreviation = models.CharField(max_length=16)
    allows_fraction = models.BooleanField(
        default=False,
        help_text="Whether quantities may have decimals (produce, weighed goods).",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "abbreviation"],
                name="uniq_unit_org_abbreviation",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.abbreviation})"


class TaxRate(BaseModel):
    """A tax band, e.g. Kenyan VAT at 16%.

    Tax lives in its own table because it changes by jurisdiction and by product
    type, and because historical sales must remain explainable after a rate
    change.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="tax_rates",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=64)
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Percentage, e.g. 16.00 for 16% VAT.",
    )
    is_inclusive = models.BooleanField(
        default=True,
        help_text="True when the listed price already contains this tax.",
    )

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_tax_rate_org_name",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class Product(SoftDeleteModel):
    """An item the organization sells.

    Belongs to the organization, not to a branch: one catalogue covers every
    branch. Stock is not part of the catalogue's identity and moves to
    ``branch_inventory`` in phase 5.

    ``stock_level`` below is a transitional column. The sales path still reads
    it, and phase 5 replaces it with per-branch inventory backed by an
    append-only movement ledger. Do not build new behaviour on it.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="products",
        on_delete=models.CASCADE,
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, blank=True, db_index=True)
    category = models.ForeignKey(
        Category,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    brand = models.ForeignKey(
        Brand,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    unit = models.ForeignKey(
        Unit,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    tax_rate = models.ForeignKey(
        TaxRate,
        null=True,
        blank=True,
        related_name="products",
        on_delete=models.SET_NULL,
    )
    price = models.DecimalField(
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Selling price. Named `price` rather than `sale_price` to avoid "
        "churning every caller for no correctness gain.",
        **MONEY,
    )
    cost_price = models.DecimalField(
        help_text="Landed cost, used for margin reporting.",
        **MONEY,
    )
    low_stock_threshold = models.PositiveIntegerField(default=10)
    track_inventory = models.BooleanField(
        default=True,
        help_text="False for services and non-stocked items.",
    )
    is_active = models.BooleanField(default=True)

    # Transitional - see the class docstring. Removed in phase 5.
    stock_level = models.IntegerField(default=0)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["organization", "name"], name="idx_product_org_name"),
        ]

    def __str__(self):
        return self.name


class ProductBarcode(BaseModel):
    """A barcode for a product.

    A table rather than a column, because real products carry several barcodes:
    the manufacturer's, the supplier's carton code, and a locally printed label.
    Uniqueness is per organization, so two shops may both stock the same EAN.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="product_barcodes",
        on_delete=models.CASCADE,
        help_text="Denormalised from the product so barcode uniqueness can be "
        "enforced per organization with a plain unique constraint.",
    )
    product = models.ForeignKey(
        Product,
        related_name="barcodes",
        on_delete=models.CASCADE,
    )
    barcode = models.CharField(max_length=64, db_index=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["barcode"]
        verbose_name = "product barcode"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "barcode"],
                name="uniq_barcode_org",
            ),
        ]

    def __str__(self):
        return self.barcode


class PriceHistory(BaseModel):
    """An audit record of a selling-price change.

    Price changes are one of the actions the brief requires to be auditable, and
    a product's current price cannot explain what it used to be.
    """

    product = models.ForeignKey(
        Product,
        related_name="price_history",
        on_delete=models.CASCADE,
    )
    old_price = models.DecimalField(**MONEY)
    new_price = models.DecimalField(**MONEY)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="price_changes",
        on_delete=models.SET_NULL,
    )
    reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "price history"

    def __str__(self):
        return f"{self.product_id}: {self.old_price} -> {self.new_price}"
