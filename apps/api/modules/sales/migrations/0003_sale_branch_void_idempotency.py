"""Branch attribution, idempotency and the void path for sales.

Written by hand rather than generated, because two of the three steps are data
work, not schema work:

1. add the columns (``organization``, ``branch``, ``client_reference``,
   ``status``, ``voided_at``, ``voided_by``, ``void_reason``);
2. backfill ``organization`` from the cashier and ``branch`` from the
   cashier's default posting, or the organization's only branch, so existing
   sales do not vanish from a branch-posted cashier's list after deploy;
3. add the ``(organization, client_reference)`` unique constraint that makes a
   retried checkout a no-op instead of a second sale.
"""

from django.db import migrations, models
from django.db.models import OuterRef, Subquery


def backfill_tenant_and_branch(apps, schema_editor):
    Sale = apps.get_model("sales", "Sale")
    Branch = apps.get_model("branches", "Branch")

    # The cashier owns the tenant; the sale inherits it.
    Sale.objects.filter(organization__isnull=True, cashier__organization__isnull=False).update(
        organization_id=Subquery(
            Sale.objects.filter(pk=OuterRef("pk")).values("cashier__organization_id")[:1]
        )
    )

    # The cashier's default branch is the best guess for where the sale was
    # rung up.
    Sale.objects.filter(branch__isnull=True, cashier__default_branch__isnull=False).update(
        branch_id=Subquery(
            Sale.objects.filter(pk=OuterRef("pk")).values("cashier__default_branch_id")[:1]
        )
    )

    # Otherwise, a single-branch organization has no ambiguity to resolve.
    organization_ids = (
        Sale.objects.filter(branch__isnull=True, organization__isnull=False)
        .values_list("organization_id", flat=True)
        .distinct()
    )
    for organization_id in list(organization_ids):
        branches = list(Branch.objects.filter(organization_id=organization_id).values_list("id", flat=True))
        if len(branches) == 1:
            Sale.objects.filter(
                branch__isnull=True, organization_id=organization_id
            ).update(branch_id=branches[0])


def clear_backfill(apps, schema_editor):
    """Reversing the migration drops the columns; nothing else to undo."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0002_saleitem_money_columns"),
        ("branches", "0001_initial"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="organization",
            field=models.ForeignKey(
                blank=True,
                help_text="Denormalised from the cashier; the tenant boundary for this row.",
                null=True,
                on_delete=models.PROTECT,
                related_name="sales",
                to="organizations.organization",
            ),
        ),
        migrations.AddField(
            model_name="sale",
            name="branch",
            field=models.ForeignKey(
                blank=True,
                help_text="Where the sale was rung up. Null only for pre-branch rows.",
                null=True,
                on_delete=models.PROTECT,
                related_name="sales",
                to="branches.branch",
            ),
        ),
        migrations.AddField(
            model_name="sale",
            name="client_reference",
            field=models.CharField(
                blank=True,
                db_index=True,
                default="",
                help_text="POS idempotency key: repeating it returns the first sale.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="sale",
            name="status",
            field=models.CharField(
                choices=[("COMPLETED", "Completed"), ("VOIDED", "Voided")],
                db_index=True,
                default="COMPLETED",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="sale",
            name="voided_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sale",
            name="voided_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.PROTECT,
                related_name="sales_voided",
                to="accounts.user",
            ),
        ),
        migrations.AddField(
            model_name="sale",
            name="void_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.RunPython(backfill_tenant_and_branch, clear_backfill),
        migrations.AddIndex(
            model_name="sale",
            index=models.Index(
                fields=["organization", "created_at"], name="idx_sale_org_created"
            ),
        ),
        migrations.AddIndex(
            model_name="sale",
            index=models.Index(
                fields=["branch", "created_at"], name="idx_sale_branch_created"
            ),
        ),
        migrations.AddConstraint(
            model_name="sale",
            constraint=models.UniqueConstraint(
                condition=~models.Q(client_reference=""),
                fields=("organization", "client_reference"),
                name="uniq_sale_org_client_ref",
            ),
        ),
    ]
