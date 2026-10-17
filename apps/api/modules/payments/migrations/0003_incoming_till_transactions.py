from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0016_accountant_inventory_read_access"),
        ("branches", "0003_till_cashsession_cashmovement_and_more"),
        ("organizations", "0002_clerk_identity"),
        ("payments", "0002_payment_refunded_status"),
        ("sales", "0005_sale_cash_session_sale_till"),
    ]

    operations = [
        migrations.CreateModel(
            name="MerchantTillAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("shortcode", models.CharField(max_length=32)),
                ("environment", models.CharField(choices=[("sandbox", "Sandbox"), ("production", "Production")], max_length=12)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="mpesa_till_accounts", to="branches.branch")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="mpesa_till_accounts", to="organizations.organization")),
            ],
            options={"ordering": ["organization__name", "shortcode"]},
        ),
        migrations.AddConstraint(
            model_name="merchanttillaccount",
            constraint=models.UniqueConstraint(fields=("shortcode", "environment"), name="uniq_mpesa_shortcode_environment"),
        ),
        migrations.CreateModel(
            name="IncomingTillTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("receipt_number", models.CharField(max_length=64)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("currency", models.CharField(default="KES", max_length=3)),
                ("transaction_time", models.DateTimeField()),
                ("payer_phone", models.CharField(blank=True, default="", max_length=32)),
                ("payer_first_name", models.CharField(blank=True, default="", max_length=80)),
                ("payer_middle_name", models.CharField(blank=True, default="", max_length=80)),
                ("payer_last_name", models.CharField(blank=True, default="", max_length=80)),
                ("bill_reference", models.CharField(blank=True, default="", max_length=64)),
                ("third_party_transaction_id", models.CharField(blank=True, default="", max_length=64)),
                ("raw_payload", models.JSONField(default=dict)),
                ("status", models.CharField(choices=[("UNMATCHED", "Unmatched"), ("MATCHED", "Matched"), ("DUPLICATE_REVIEW", "Duplicate review"), ("REJECTED", "Rejected")], db_index=True, default="UNMATCHED", max_length=20)),
                ("matched_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="transactions", to="payments.merchanttillaccount")),
                ("matched_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="matched_till_transactions", to=settings.AUTH_USER_MODEL)),
                ("matched_payment", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="matched_till_transaction", to="payments.payment")),
                ("matched_sale", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="matched_till_transactions", to="sales.sale")),
            ],
            options={"ordering": ["-transaction_time", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="incomingtilltransaction",
            constraint=models.UniqueConstraint(fields=("account", "receipt_number"), name="uniq_till_receipt_per_account"),
        ),
        migrations.AddIndex(
            model_name="incomingtilltransaction",
            index=models.Index(fields=["account", "status", "transaction_time"], name="idx_till_txn_queue"),
        ),
    ]
