from django.db import migrations

# ``0003_seed_rbac`` is a historical snapshot and is left exactly as it was
# applied. New permission codes are added by later migrations like this one,
# so the vocabulary can grow without rewriting migration history.

PERMISSIONS = [
    ("expenses.view", "expenses", "View expenses and expense categories"),
    ("expenses.manage", "expenses", "Record and reverse expenses"),
]

# Granting follows the existing role vocabulary:
#
# - expenses.view: spend is operational information — managers, supervisors
#   (their branch's ledger) and accountants all read it; cashiers do not,
#   for the same reason they do not hold cash.review.
# - expenses.manage: recording or reversing spend is a financial act.
#   Accountants hold it because entering the ledger is their job; cashiers
#   do not, so a drawer and the ledger around it are never touched by the
#   same hands by default.
GRANTED_TO = {
    "expenses.view": ["SUPER_ADMIN", "ADMIN", "MANAGER", "SUPERVISOR", "ACCOUNTANT"],
    "expenses.manage": ["SUPER_ADMIN", "ADMIN", "MANAGER", "ACCOUNTANT"],
}


def grant_expense_permissions(apps, schema_editor):
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


def revoke_expense_permissions(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code__in=[code for code, _, _ in PERMISSIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_till_cash_permissions"),
    ]

    operations = [
        migrations.RunPython(grant_expense_permissions, revoke_expense_permissions),
    ]
