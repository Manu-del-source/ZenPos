from django.db import migrations, models


class Migration(migrations.Migration):
    """Add ``Role.permissions``.

    Deliberately a separate migration from ``0001_initial``: the many-to-many
    uses an explicit ``through`` model, and adding it afterwards guarantees the
    through table already exists in migration state. The resulting end state is
    identical to declaring the field inline, which is what the model does.
    """

    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="role",
            name="permissions",
            field=models.ManyToManyField(
                blank=True,
                related_name="roles",
                through="accounts.RolePermission",
                to="accounts.permission",
            ),
        ),
    ]
