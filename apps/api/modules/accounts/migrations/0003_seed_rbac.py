from django.db import migrations

# The granular permission vocabulary. These are infrastructure, not user data:
# authorization is written against these codes, so they ship with the schema
# rather than being created by hand at deploy time.
PERMISSIONS = [
    ("users.manage", "accounts", "Create, edit and deactivate staff accounts"),
    ("branches.manage", "branches", "Create and edit branches"),
    ("settings.manage", "core", "Change organization-wide settings"),
    ("products.view", "catalog", "View the product catalogue"),
    ("products.create", "catalog", "Add products to the catalogue"),
    ("products.update", "catalog", "Edit products and their prices"),
    ("inventory.view", "inventory", "View stock levels and movements"),
    ("inventory.adjust", "inventory", "Record stock adjustments"),
    ("inventory.transfer", "inventory", "Transfer stock between branches"),
    ("purchases.create", "purchasing", "Raise purchase orders and receive goods"),
    ("sales.create", "sales", "Complete a sale at the point of sale"),
    ("sales.view", "sales", "View sales and receipts"),
    ("sales.refund", "sales", "Authorise returns and refunds"),
    ("customers.manage", "customers", "Create and edit customer records"),
    ("loyalty.manage", "loyalty", "Adjust loyalty balances"),
    ("reports.view", "reporting", "View reports and dashboards"),
]

ALL_PERMISSIONS = [code for code, _, _ in PERMISSIONS]

# System roles are organizations=None, so every organization gets them. They are
# starting points: an organization may add its own roles alongside them.
ROLE_DEFINITIONS = [
    ("SUPER_ADMIN", "Full control of the platform", ALL_PERMISSIONS),
    ("ADMIN", "Full control of one organization", ALL_PERMISSIONS),
    (
        "MANAGER",
        "Runs a branch or a group of branches",
        [
            "users.manage",
            "branches.manage",
            "products.view",
            "products.create",
            "products.update",
            "inventory.view",
            "inventory.adjust",
            "inventory.transfer",
            "purchases.create",
            "sales.create",
            "sales.view",
            "sales.refund",
            "customers.manage",
            "loyalty.manage",
            "reports.view",
        ],
    ),
    (
        "SUPERVISOR",
        "Supervises cashiers on a shift",
        [
            "products.view",
            "inventory.view",
            "inventory.adjust",
            "sales.create",
            "sales.view",
            "sales.refund",
            "customers.manage",
            "reports.view",
        ],
    ),
    (
        "CASHIER",
        "Operates a till",
        [
            "products.view",
            "inventory.view",
            "sales.create",
            "sales.view",
            "customers.manage",
        ],
    ),
    (
        "INVENTORY_MANAGER",
        "Owns stock accuracy and purchasing",
        [
            "products.view",
            "products.create",
            "products.update",
            "inventory.view",
            "inventory.adjust",
            "inventory.transfer",
            "purchases.create",
            "reports.view",
        ],
    ),
    (
        "ACCOUNTANT",
        "Financial oversight and reporting",
        ["sales.view", "inventory.view", "reports.view"],
    ),
]


def seed_rbac(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    RolePermission = apps.get_model("accounts", "RolePermission")

    permissions = {}
    for code, module, description in PERMISSIONS:
        permission, _ = Permission.objects.update_or_create(
            code=code,
            defaults={"module": module, "description": description},
        )
        permissions[code] = permission

    for name, description, codes in ROLE_DEFINITIONS:
        role, _ = Role.objects.update_or_create(
            organization=None,
            name=name,
            defaults={"description": description, "is_system": True},
        )
        for code in codes:
            RolePermission.objects.get_or_create(
                role=role,
                permission=permissions[code],
            )


def remove_rbac(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    Permission = apps.get_model("accounts", "Permission")

    Role.objects.filter(organization__isnull=True).delete()
    Permission.objects.filter(code__in=ALL_PERMISSIONS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_role_permissions"),
    ]

    operations = [
        migrations.RunPython(seed_rbac, remove_rbac),
    ]
