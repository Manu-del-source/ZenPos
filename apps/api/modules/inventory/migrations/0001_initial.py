import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("accounts", "0001_initial"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="StockAdjustment",
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
                    "quantity",
                    models.IntegerField(
                        help_text="Positive adds stock, negative removes it."
                    ),
                ),
                (
                    "type",
                    models.CharField(
                        choices=[
                            ("RESTOCK", "Restock/Purchase"),
                            ("DAMAGE", "Damaged Goods"),
                            ("RETURN", "Customer Return"),
                            ("ADJUST", "Manual Adjustment"),
                            ("EXPIRE", "Expired Goods"),
                        ],
                        max_length=10,
                    ),
                ),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="adjustments",
                        to="catalog.product",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-id"],
            },
        ),
    ]
