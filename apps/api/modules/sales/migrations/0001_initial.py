import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("catalog", "0001_initial"),
        ("customers", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Sale",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "sale_number",
                    models.CharField(db_index=True, max_length=50, unique=True),
                ),
                ("total_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                ("tax_amount", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "discount_amount",
                    models.DecimalField(decimal_places=2, default=0, max_digits=10),
                ),
                (
                    "payment_method",
                    models.CharField(
                        choices=[
                            ("CASH", "Cash"),
                            ("MPESA", "M-Pesa"),
                            ("SPLIT", "Split Payment"),
                        ],
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "cashier",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="customers.customer",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="SaleItem",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("quantity", models.IntegerField()),
                ("unit_price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("subtotal", models.DecimalField(decimal_places=2, max_digits=10)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="catalog.product",
                    ),
                ),
                (
                    "sale",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="items",
                        to="sales.sale",
                    ),
                ),
            ],
        ),
    ]
