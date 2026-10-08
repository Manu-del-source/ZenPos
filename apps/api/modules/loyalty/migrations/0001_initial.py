import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("organizations", "0001_initial"),
        ("customers", "0002_customer_organization"),
        ("branches", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="LoyaltyRule",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "amount",
                    models.DecimalField(
                        decimal_places=2,
                        default=100,
                        help_text="KES per point. 100 means 1 point per KES 100.",
                        max_digits=12,
                    ),
                ),
                ("points", models.PositiveIntegerField(default=1)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "organization",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loyalty_rule",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={"verbose_name": "loyalty rule"},
        ),
        migrations.CreateModel(
            name="LoyaltyAccount",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("points_balance", models.IntegerField(default=0)),
                (
                    "customer",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loyalty_account",
                        to="customers.customer",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loyalty_accounts",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={"ordering": ["-updated_at"]},
        ),
        migrations.CreateModel(
            name="LoyaltyLedger",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("points", models.IntegerField(help_text="Signed. Positive credits the account.")),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("EARN", "Earn"),
                            ("REDEEM", "Redeem"),
                            ("ADJUST", "Adjust"),
                            ("REVERSAL", "Reversal"),
                            ("EXPIRE", "Expire"),
                        ],
                        db_index=True,
                        max_length=12,
                    ),
                ),
                ("reference_type", models.CharField(blank=True, default="", max_length=32)),
                ("reference_id", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("notes", models.TextField(blank=True, default="")),
                ("balance_after", models.IntegerField()),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="entries",
                        to="loyalty.loyaltyaccount",
                    ),
                ),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="loyalty_entries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="loyalty_entries",
                        to="branches.branch",
                    ),
                ),
                (
                    "customer",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loyalty_entries",
                        to="customers.customer",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="loyalty_ledger",
                        to="organizations.organization",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"], "verbose_name_plural": "loyalty ledger"},
        ),
        migrations.AddConstraint(
            model_name="loyaltyledger",
            constraint=models.UniqueConstraint(
                condition=~models.Q(("reference_id", "")),
                fields=("organization", "action", "reference_type", "reference_id"),
                name="uniq_loyalty_org_action_ref",
            ),
        ),
        migrations.AddIndex(
            model_name="loyaltyledger",
            index=models.Index(fields=["customer", "created_at"], name="idx_loyal_cust_created"),
        ),
    ]
