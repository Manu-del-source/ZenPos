from django.db import migrations


def seed_hr_manager(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")
    RolePermission = apps.get_model("accounts", "RolePermission")

    manage_users = Permission.objects.get(code="users.manage")
    view_branches = Permission.objects.get(code="branches.view")
    role, _ = Role.objects.update_or_create(
        organization=None,
        name="HR_MANAGER",
        defaults={
            "description": "Manages employee accounts and delegates only the access they hold",
            "is_system": True,
        },
    )
    RolePermission.objects.get_or_create(role=role, permission=manage_users)
    RolePermission.objects.get_or_create(role=role, permission=view_branches)


def remove_hr_manager(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    UserRole = apps.get_model("accounts", "UserRole")
    role = Role.objects.filter(organization__isnull=True, name="HR_MANAGER").first()
    # Do not remove a role that has been assigned to users during a rollback.
    if role and not UserRole.objects.filter(role=role).exists():
        role.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0013_clerk_identity"),
    ]

    operations = [
        migrations.RunPython(seed_hr_manager, remove_hr_manager),
    ]
