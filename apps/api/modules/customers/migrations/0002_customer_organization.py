from django.db import migrations, models
import django.db.models.deletion


def assign_default_organization(apps, schema_editor):
    """Attach pre-phase-4 customers to an organization.

    Customers were created before multi-tenancy existed, so they have no
    organization and the column cannot be made non-null until they do. The table
    is expected to be empty — the rebuild has never been deployed — but this
    still runs, because a migration that assumes empty tables is a migration that
    fails on somebody's machine.

    The first organization is the only defensible guess. If customers exist and
    no organization does, there is no correct answer, so the migration says so
    rather than inventing one.
    """
    Customer = apps.get_model("customers", "Customer")
    Organization = apps.get_model("organizations", "Organization")

    orphans = Customer.objects.filter(organization__isnull=True)
    if not orphans.exists():
        return

    organization = Organization.objects.order_by("created_at", "id").first()
    if organization is None:
        raise RuntimeError(
            "Customers exist but no organization does. Create an organization "
            "before running this migration."
        )

    orphans.update(organization=organization)


class Migration(migrations.Migration):

    dependencies = [
        ("customers", "0001_initial"),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customer",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="customers",
                to="organizations.organization",
            ),
        ),
        migrations.RunPython(assign_default_organization, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="customer",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="customers",
                to="organizations.organization",
            ),
        ),
        # Uniqueness moves from "this phone number anywhere in the platform" to
        # "this phone number within this shop's organization".
        migrations.AlterField(
            model_name="customer",
            name="phone",
            field=models.CharField(db_index=True, max_length=15),
        ),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(
                fields=("organization", "phone"),
                name="uniq_customer_org_phone",
            ),
        ),
    ]
