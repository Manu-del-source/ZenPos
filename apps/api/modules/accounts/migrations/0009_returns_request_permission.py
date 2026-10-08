from django.db import migrations

RETURNS_REQUEST = (
    "returns.request",
    "sales",
    "Request a return against a completed sale",
)

# Cashiers request; supervisors and above already hold sales.refund to approve.
GRANTED_TO = ["SUPER_ADMIN", "ADMIN", "MANAGER", "SUPERVISOR", "CASHIER"]


def grant(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")
    code, module, description = RETURNS_REQUEST
    permission, _ = Permission.objects.update_or_create(
        code=code, defaults={"module": module, "description": description}
    )
    for role in Role.objects.filter(name__in=GRANTED_TO, organization__isnull=True):
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code=RETURNS_REQUEST[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_purchases_receive_permission"),
    ]

    operations = [migrations.RunPython(grant, revoke)]
