from django.db import migrations

# ``audit.view`` joins the permission vocabulary the same way ``branches.view``
# did in 0004: seeded by a dedicated migration so the code, the grant and the
# check ship together (ADR-0008).
AUDIT_VIEW = ("audit.view", "audit", "Read the audit log")

# Reading the audit log is a governance act: it exposes who did what across the
# whole organization, including permission changes. Owners and finance see it;
# MANAGER is excluded because a manager must not be able to read the evidence
# of their own privilege changes.
GRANTED_TO = ["SUPER_ADMIN", "ADMIN", "ACCOUNTANT"]


def grant_audit_view(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    code, module, description = AUDIT_VIEW
    permission, _ = Permission.objects.update_or_create(
        code=code,
        defaults={"module": module, "description": description},
    )

    roles = Role.objects.filter(name__in=GRANTED_TO, organization__isnull=True)
    for role in roles:
        RolePermission.objects.get_or_create(role=role, permission=permission)


def revoke_audit_view(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code=AUDIT_VIEW[0]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_branches_view_permission"),
    ]

    operations = [
        migrations.RunPython(grant_audit_view, revoke_audit_view),
    ]
