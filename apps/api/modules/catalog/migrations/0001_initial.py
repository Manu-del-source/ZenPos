import django.core.validators
import django.db.models.deletion
import uuid

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Brand",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="brands",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "name"),
                        name="uniq_brand_org_name",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="categories",
                        to="organizations.organization",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="children",
                        to="catalog.category",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "categories",
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "parent", "name"),
                        name="uniq_category_org_parent_name",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("parent__isnull", True)),
                        fields=("organization", "name"),
                        name="uniq_root_category_org_name",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Unit",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                ("abbreviation", models.CharField(max_length=16)),
                (
                    "allows_fraction",
                    models.BooleanField(
                        default=False,
                        help_text="Whether quantities may have decimals (produce, weighed goods).",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="units",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "abbreviation"),
                        name="uniq_unit_org_abbreviation",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="TaxRate",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=64)),
                (
                    "rate",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Percentage, e.g. 16.00 for 16% VAT.",
                        max_digits=5,
                        validators=[django.core.validators.MinValueValidator(Decimal("0"))],
                    ),
                ),
                (
                    "is_inclusive",
                    models.BooleanField(
                        default=True,
                        help_text="True when the listed price already contains this tax.",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tax_rates",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "name"),
                        name="uniq_tax_rate_org_name",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="Product",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("name", models.CharField(max_length=255)),
                ("sku", models.CharField(blank=True, db_index=True, max_length=64)),
                (
                    "price",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Selling price. Named `price` rather than `sale_price` to avoid churning every caller for no correctness gain.",
                        max_digits=14,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.01"))
                        ],
                    ),
                ),
                (
                    "cost_price",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Landed cost, used for margin reporting.",
                        max_digits=14,
                    ),
                ),
                ("low_stock_threshold", models.PositiveIntegerField(default=10)),
                (
                    "track_inventory",
                    models.BooleanField(
                        default=True,
                        help_text="False for services and non-stocked items.",
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("stock_level", models.IntegerField(default=0)),
                (
                    "brand",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="catalog.brand",
                    ),
                ),
                (
                    "category",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="catalog.category",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="products",
                        to="organizations.organization",
                    ),
                ),
                (
                    "tax_rate",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="catalog.taxrate",
                    ),
                ),
                (
                    "unit",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="products",
                        to="catalog.unit",
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
                "indexes": [
                    models.Index(
                        fields=["organization", "name"],
                        name="idx_product_org_name",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="ProductBarcode",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("barcode", models.CharField(db_index=True, max_length=64)),
                ("is_primary", models.BooleanField(default=False)),
                (
                    "organization",
                    models.ForeignKey(
                        help_text="Denormalised from the product so barcode uniqueness can be enforced per organization with a plain unique constraint.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_barcodes",
                        to="organizations.organization",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="barcodes",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "verbose_name": "product barcode",
                "ordering": ["barcode"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "barcode"),
                        name="uniq_barcode_org",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="PriceHistory",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("old_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("new_price", models.DecimalField(decimal_places=2, max_digits=14)),
                ("reason", models.CharField(blank=True, max_length=255)),
                (
                    "changed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="accounts.user",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_history",
                        to="catalog.product",
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "price history",
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
