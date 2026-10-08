from django.db import migrations

PURCHASES_RECEIVE = (
    "purchases.receive",
    "purchasing",
    "Post goods received notes and update inventory",
)

GRANTED_TO = ["SUPER_ADMIN", "ADMIN", "MANAGER", "INVENTORY_MANAGER"]


def grant_purchases_receive(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    code, module, description = PURCHASES_RECEIVE
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={"module": module, "description": description},
    )

    roles = Role.objects.filter(name__in=GRANTED_TO, organization__isnull=True)
    for role in roles:
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_purchases_receive(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code=PURCHASES_RECEIVE[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_purchases_approve_permission"),
    ]

    operations = [
        migrations.RunPython(grant_purchases_receive, revoke_purchases_receive),
    ]
