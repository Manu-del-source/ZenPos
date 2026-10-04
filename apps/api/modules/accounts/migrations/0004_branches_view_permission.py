from django.db import migrations

# ``0003_seed_rbac`` is a historical snapshot and is left exactly as it was
# applied. New permission codes are added by later migrations like this one, so
# the vocabulary can grow without rewriting migration history.
BRANCH_VIEW = ("branches.view", "branches", "View branches")

# Every role needs to read branch names: a cashier's till belongs to one, and a
# receipt prints one. Reading them is not a privileged act, so all seven system
# roles get this.
GRANTED_TO = [
    "SUPER_ADMIN",
    "ADMIN",
    "MANAGER",
    "SUPERVISOR",
    "CASHIER",
    "INVENTORY_MANAGER",
    "ACCOUNTANT",
]


def grant_branch_view(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    code, module, description = BRANCH_VIEW
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={"module": module, "description": description},
    )

    roles = Role.objects.filter(name__in=GRANTED_TO, organization__isnull=True)
    for role in roles:
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_branch_view(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    code = BRANCH_VIEW[0]
    Permission.objects.filter(code=code).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_seed_rbac"),
    ]

    operations = [
        migrations.RunPython(grant_branch_view, revoke_branch_view),
    ]
