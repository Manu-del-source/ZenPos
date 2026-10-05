from django.db import migrations

# ``purchases.view`` joins the permission vocabulary the same way
# ``branches.view`` (0004) and ``audit.view`` (0005) did: seeded by a dedicated
# migration so the code, the grant and the check ship together. The supplier
# directory is the first object guarded by it; purchase orders and receiving
# follow the same code.
PURCHASES_VIEW = (
    "purchases.view",
    "purchasing",
    "View suppliers and purchase records",
)

# The same roles that already hold ``purchases.create``: the people who raise
# orders are the people who read the directory. ACCOUNTANT is excluded,
# matching the existing purchasing grant set.
GRANTED_TO = ["SUPER_ADMIN", "ADMIN", "MANAGER", "INVENTORY_MANAGER"]


def grant_purchases_view(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    code, module, description = PURCHASES_VIEW
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={"module": module, "description": description},
    )

    roles = Role.objects.filter(name__in=GRANTED_TO, organization__isnull=True)
    for role in roles:
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_purchases_view(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code=PURCHASES_VIEW[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_audit_view_permission"),
    ]

    operations = [
        migrations.RunPython(grant_purchases_view, revoke_purchases_view),
    ]
