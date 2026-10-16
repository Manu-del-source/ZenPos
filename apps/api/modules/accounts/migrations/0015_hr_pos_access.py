from django.db import migrations


# HR can use the till and the catalogue, but does not receive reports,
# refunds, pricing administration, inventory adjustments, or business settings.
HR_POS_PERMISSIONS = (
    "sales.create",
    "products.view",
    "inventory.view",
    "customers.manage",
)


def grant_hr_pos_access(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    role = Role.objects.filter(organization__isnull=True, name="HR_MANAGER").first()
    if role is None:
        return

    permissions = Permission.objects.filter(code__in=HR_POS_PERMISSIONS)
    for permission in permissions:
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_hr_pos_access(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    role = Role.objects.filter(organization__isnull=True, name="HR_MANAGER").first()
    if role is None:
        return

    RolePermission.objects.filter(
        role=role,
        permission__code__in=HR_POS_PERMISSIONS,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_seed_hr_manager"),
    ]

    operations = [
        migrations.RunPython(grant_hr_pos_access, revoke_hr_pos_access),
    ]
