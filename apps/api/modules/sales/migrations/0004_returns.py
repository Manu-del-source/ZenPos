from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0003_sale_branch_void_idempotency"),
        ("catalog", "0003_alter_product_managers"),
        ("customers", "0002_customer_organization"),
        ("branches", "0001_initial"),
        ("organizations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="saleitem",
            name="quantity_returned",
            field=models.IntegerField(
                default=0,
                help_text="Cumulative quantity posted through completed returns.",
            ),
        ),
        migrations.CreateModel(
            name="SaleReturn",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(db_index=True, max_length=50, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("REQUESTED", "Requested"),
                            ("AUTHORIZED", "Authorized"),
                            ("COMPLETED", "Completed"),
                            ("REJECTED", "Rejected"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        db_index=True,
                        default="REQUESTED",
                        max_length=12,
                    ),
                ),
                (
                    "reason",
                    models.CharField(
                        choices=[
                            ("DAMAGED", "Damaged"),
                            ("WRONG_ITEM", "Wrong item"),
                            ("CUSTOMER_CHANGE", "Customer changed mind"),
                            ("EXPIRED", "Expired"),
                            ("OTHER", "Other"),
                        ],
                        max_length=20,
                    ),
                ),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "refund_method",
                    models.CharField(
                        choices=[
                            ("CASH", "Cash"),
                            ("MPESA", "M-Pesa"),
                            ("STORE_CREDIT", "Store credit"),
                        ],
                        default="CASH",
                        max_length=16,
                    ),
                ),
                ("refund_amount", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("authorized_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "authorized_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="returns_authorized",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sale_returns",
                        to="branches.branch",
                    ),
                ),
                (
                    "completed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="returns_completed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="returns",
                        to="customers.customer",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sale_returns",
                        to="organizations.organization",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="returns_requested",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "sale",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="returns",
                        to="sales.sale",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="SaleReturnLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("original_quantity", models.IntegerField()),
                ("already_returned", models.IntegerField(default=0)),
                ("quantity", models.IntegerField()),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("line_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "restock",
                    models.BooleanField(
                        default=True,
                        help_text="False sends the units to damaged rather than sellable stock.",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="catalog.product"),
                ),
                (
                    "sale_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="return_lines",
                        to="sales.saleitem",
                    ),
                ),
                (
                    "sale_return",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="sales.salereturn",
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
        migrations.AddIndex(
            model_name="salereturn",
            index=models.Index(fields=["organization", "created_at"], name="idx_return_org_created"),
        ),
        migrations.AddIndex(
            model_name="salereturn",
            index=models.Index(fields=["sale", "status"], name="idx_return_sale_status"),
        ),
        migrations.AddConstraint(
            model_name="salereturnline",
            constraint=models.UniqueConstraint(
                fields=("sale_return", "sale_item"), name="uniq_return_line_sale_item"
            ),
        ),
    ]
