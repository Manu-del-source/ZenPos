from django.db import migrations

# ``0003_seed_rbac`` is a historical snapshot and is left exactly as it was
# applied. New permission codes are added by later migrations like this one,
# so the vocabulary can grow without rewriting migration history.

PERMISSIONS = [
    ("tills.manage", "branches", "Create and manage tills"),
    ("cash.open", "branches", "Open a till cash session"),
    ("cash.close", "branches", "Close a till cash session with a physical count"),
    ("cash.adjust", "branches", "Record manual cash movements on a session"),
    ("cash.review", "branches", "View cash session reconciliation and review sessions"),
]

# Granting follows the existing role vocabulary:
#
# - tills.manage: management act, like branches.manage.
# - cash.open / cash.close: every role that works a till needs both — a
#   cashier opens and closes their own shift; a supervisor does the same on
#   their branch and can close a cashier's session.
# - cash.adjust: manual cash leaving or entering the drawer (drops, payouts)
#   is a supervised act, so CASHIER does not hold it by default. An
#   organization can grant it through a custom role if it wishes.
# - cash.review: reconciliation is supervisory and financial — supervisors and
#   accountants read it; cashiers see their own drawer through the till, not
#   through the review endpoints.
GRANTED_TO = {
    "tills.manage": ["SUPER_ADMIN", "ADMIN", "MANAGER"],
    "cash.open": ["SUPER_ADMIN", "ADMIN", "MANAGER", "SUPERVISOR", "CASHIER"],
    "cash.close": ["SUPER_ADMIN", "ADMIN", "MANAGER", "SUPERVISOR", "CASHIER"],
    "cash.adjust": ["SUPER_ADMIN", "ADMIN", "MANAGER", "SUPERVISOR"],
    "cash.review": ["SUPER_ADMIN", "ADMIN", "MANAGER", "SUPERVISOR", "ACCOUNTANT"],
}


def grant_till_cash_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    for code, module, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={"module": module, "description": description},
        )
        roles = Role.objects.filter(
            name__in=GRANTED_TO[code], organization__isnull=True
        )
        for role in roles:
            RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_till_cash_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code__in=[code for code, _, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_employee"),
    ]

    operations = [
        migrations.RunPython(grant_till_cash_permissions, revoke_till_cash_permissions),
    ]
