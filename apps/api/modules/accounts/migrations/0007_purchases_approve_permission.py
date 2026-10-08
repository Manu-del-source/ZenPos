from django.db import migrations

# Approving money leaving the shop is a different decision from raising the
# order. ``purchases.create`` (0003) covers raising, submitting and cancelling;
# ``purchases.approve`` is held by whoever signs the order off. It ships the
# same way the rest of the vocabulary did: seeded here, granted to the seeded
# roles listed below, checked by the views that ship with it.
PURCHASES_APPROVE = (
    "purchases.approve",
    "purchasing",
    "Approve purchase orders for receiving",
)

# MANAGER already holds purchases.create and runs branches; ADMIN and
# SUPER_ADMIN sign off at head office. INVENTORY_MANAGER raises orders but does
# not approve their own request to spend — separation of duties by default,
# adjustable by granting the code to a custom role.
GRANTED_TO = ["SUPER_ADMIN", "ADMIN", "MANAGER"]


def grant_purchases_approve(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    code, module, description = PURCHASES_APPROVE
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={"module": module, "description": description},
    )

    roles = Role.objects.filter(name__in=GRANTED_TO, organization__isnull=True)
    for role in roles:
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_purchases_approve(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code=PURCHASES_APPROVE[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_purchases_view_permission"),
    ]

    operations = [
        migrations.RunPython(grant_purchases_approve, revoke_purchases_approve),
    ]
