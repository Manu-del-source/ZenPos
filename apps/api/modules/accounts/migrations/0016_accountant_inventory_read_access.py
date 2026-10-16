from django.db import migrations


# Accountants need to inspect the product catalogue to reconcile stock and
# inventory valuation. This is read-only access: it does not grant product
# creation/updates or stock adjustments/transfers.
ACCOUNTANT_INVENTORY_READ_PERMISSIONS = ("products.view",)


def grant_accountant_inventory_read_access(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    role = Role.objects.filter(
        organization__isnull=True,
        name="ACCOUNTANT",
        is_system=True,
    ).first()
    if role is None:
        return

    for permission in Permission.objects.filter(
        code__in=ACCOUNTANT_INVENTORY_READ_PERMISSIONS
    ):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_accountant_inventory_read_access(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    role = Role.objects.filter(
        organization__isnull=True,
        name="ACCOUNTANT",
        is_system=True,
    ).first()
    if role is None:
        return

    RolePermission.objects.filter(
        role=role,
        permission__code__in=ACCOUNTANT_INVENTORY_READ_PERMISSIONS,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0015_hr_pos_access"),
    ]

    operations = [
        migrations.RunPython(
            grant_accountant_inventory_read_access,
            revoke_accountant_inventory_read_access,
        ),
    ]
