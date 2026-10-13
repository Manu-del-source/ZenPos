"""Customers: archive (soft delete) and move the points balance to the ledger.

The legacy ``loyalty_points`` column is a mutable balance that the phase-8
loyalty ledger supersedes: the account's ``points_balance`` is maintained
transactionally with an append-only explanation for every change, and the
customer column could drift from it. Existing balances are carried over into
LoyaltyAccount with a single ADJUST ledger entry naming the source, so no
points are destroyed — the ledger remains the single source of truth, and the
column is then dropped.

``deleted_at`` lets a customer be archived (hidden from the directory) without
breaking the sales history that points at them. The org+phone unique
constraint becomes conditional on the row being live, the same way the
supplier directory works, so archiving a customer frees their phone number
for the next holder.
"""

from decimal import Decimal

from django.db import migrations, models

from modules.core.managers import AllObjectsManager, SoftDeleteManager


def carry_balances_to_ledger(apps, schema_editor):
    """Move every existing legacy balance into its loyalty account."""
    Customer = apps.get_model("customers", "Customer")
    LoyaltyAccount = apps.get_model("loyalty", "LoyaltyAccount")
    LoyaltyLedger = apps.get_model("loyalty", "LoyaltyLedger")

    for customer in Customer.objects.filter(loyalty_points__gt=0):
        account, _created = LoyaltyAccount.objects.get_or_create(
            customer=customer,
            defaults={
                "organization": customer.organization,
                "points_balance": Decimal("0"),
            },
        )
        account.points_balance = customer.loyalty_points
        account.save(update_fields=["points_balance"])
        LoyaltyLedger.objects.create(
            organization=customer.organization,
            account=account,
            customer=customer,
            points=customer.loyalty_points,
            action=LoyaltyLedger.Action.ADJUST,
            reference_type="legacy_balance",
            reference_id="",
            notes="Existing customer balance carried over to the loyalty ledger.",
            balance_after=customer.loyalty_points,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0002_customer_organization"),
        ("loyalty", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="deleted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.RunPython(carry_balances_to_ledger, migrations.RunPython.noop),
        # Archiving frees the phone number, like the supplier directory: the
        # uniqueness promise applies to live rows only.
        migrations.RemoveConstraint(
            model_name="customer",
            name="uniq_customer_org_phone",
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True),
                fields=["organization", "phone"],
                name="uniq_customer_org_phone",
            ),
        ),
        migrations.RemoveField(
            model_name="customer",
            name="loyalty_points",
        ),
        migrations.AlterModelManagers(
            name="customer",
            managers=[
                ("objects", SoftDeleteManager()),
                ("all_objects", AllObjectsManager()),
            ],
        ),
    ]
