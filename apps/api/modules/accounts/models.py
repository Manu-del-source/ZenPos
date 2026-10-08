from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from modules.core.models import BaseModel, SoftDeleteModel


class RoleQuerySet(models.QuerySet):
    """Role lookups that respect the tenant boundary."""

    def visible_to(self, user):
        """System roles plus the user's own organization's roles.

        A user must be able to see a role to be given it. Platform staff see
        every organization's roles, matching how the rest of the API treats
        superusers.
        """
        if getattr(user, "is_superuser", False):
            return self

        organization_id = getattr(user, "organization_id", None)
        if organization_id is None:
            return self.filter(organization__isnull=True)

        return self.filter(
            models.Q(organization__isnull=True) | models.Q(organization_id=organization_id)
        )


class User(BaseModel, AbstractUser):
    """A staff member.

    Replaces the previous ``role`` string and ``branch_name`` text field with
    real relationships. A user belongs to one organization, may be posted to
    several branches, and holds configurable roles that carry permissions.

    ``organization`` is nullable so a platform operator account can exist
    without belonging to a shop. ``createsuperuser`` would otherwise be
    impossible to run before any organization has been created.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        related_name="users",
        on_delete=models.PROTECT,
    )
    default_branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        related_name="default_for_users",
        on_delete=models.SET_NULL,
    )

    class Meta:
        ordering = ["username"]
        verbose_name = "user"
        verbose_name_plural = "users"

    def role_names(self):
        """Names of the roles granted to this user, at any scope."""
        return sorted({link.role.name for link in self.user_roles.all()})

    def permission_codes(self):
        """Permission codes held at any branch scope.

        Thin wrapper for templates and the admin; the API goes through
        ``accounts.permissions`` so there is one implementation.
        """
        from .permissions import permission_codes_for

        return permission_codes_for(self)

    def __str__(self):
        return self.get_username()


class Permission(BaseModel):
    """A single granular capability, named ``resource.action``.

    Rows are seeded by a data migration and are not user-editable in normal
    operation: they are the vocabulary that authorization is written against.

    Note this is deliberately distinct from ``django.contrib.auth.Permission``,
    which models per-model CRUD and is not what this platform authorizes on.
    """

    code = models.CharField(max_length=64, unique=True)
    module = models.CharField(max_length=32)
    description = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(BaseModel):
    """A named bundle of permissions.

    ``organization`` is null for the system roles shipped with the platform.
    Organizations may add their own roles alongside them, which is why the
    role list is data rather than a hard-coded enum.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        null=True,
        blank=True,
        related_name="roles",
        on_delete=models.CASCADE,
        help_text="Null for a system role shared by all organizations.",
    )
    name = models.CharField(max_length=64)
    description = models.CharField(max_length=255, blank=True)
    is_system = models.BooleanField(default=False)
    permissions = models.ManyToManyField(
        Permission,
        through="accounts.RolePermission",
        related_name="roles",
        blank=True,
    )

    objects = RoleQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "name"],
                name="uniq_role_org_name",
            ),
            # Postgres treats NULLs as distinct, so the constraint above does not
            # prevent duplicate system roles. This partial index does.
            models.UniqueConstraint(
                fields=["name"],
                condition=models.Q(organization__isnull=True),
                name="uniq_system_role_name",
            ),
        ]

    def __str__(self):
        return self.name


class RolePermission(BaseModel):
    role = models.ForeignKey(
        Role,
        related_name="role_permissions",
        on_delete=models.CASCADE,
    )
    permission = models.ForeignKey(
        Permission,
        related_name="role_permissions",
        on_delete=models.CASCADE,
    )

    class Meta:
        ordering = ["role__name", "permission__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission"],
                name="uniq_role_permission",
            ),
        ]

    def __str__(self):
        return f"{self.role.name}: {self.permission.code}"


class UserRole(BaseModel):
    """Grants a role to a user, either organization-wide or at one branch.

    ``branch`` null means the grant applies wherever the user can work. A
    non-null branch means the grant applies only there, which is how a
    supervisor can manage one shop but not the others.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="user_roles",
        on_delete=models.CASCADE,
    )
    role = models.ForeignKey(
        Role,
        related_name="user_roles",
        on_delete=models.CASCADE,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        related_name="user_roles",
        on_delete=models.CASCADE,
    )

    class Meta:
        ordering = ["user__username", "role__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "branch"],
                name="uniq_user_role_branch",
            ),
            models.UniqueConstraint(
                fields=["user", "role"],
                condition=models.Q(branch__isnull=True),
                name="uniq_user_role_org_wide",
            ),
        ]

    def __str__(self):
        scope = self.branch.name if self.branch_id else "all branches"
        return f"{self.user} -> {self.role.name} ({scope})"


class UserBranchAccess(BaseModel):
    """A branch a user is allowed to sign in to.

    Kept separate from role assignment on purpose. "Where may this person work"
    and "what may this person do" are different questions: a manager may hold a
    MANAGER role organization-wide while only being posted to two branches.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="branch_access",
        on_delete=models.CASCADE,
    )
    branch = models.ForeignKey(
        "branches.Branch",
        related_name="user_access",
        on_delete=models.CASCADE,
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Preselected branch for this user at the POS.",
    )

    class Meta:
        ordering = ["user__username", "branch__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "branch"],
                name="uniq_user_branch_access",
            ),
        ]
        verbose_name_plural = "user branch access"

    def __str__(self):
        return f"{self.user} @ {self.branch.name}"


class Employee(SoftDeleteModel):
    """A retail staff record, optionally linked to a login account.

    The user account is how someone signs in. This row is how the shop talks
    about them as an employee: number, status, start date. Biometric or
    smart-card identifiers belong here later, not on User.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        SUSPENDED = "SUSPENDED", "Suspended"
        TERMINATED = "TERMINATED", "Terminated"

    organization = models.ForeignKey(
        "organizations.Organization",
        related_name="employees",
        on_delete=models.CASCADE,
    )
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        related_name="employee",
        on_delete=models.SET_NULL,
    )
    employee_number = models.CharField(max_length=32)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        related_name="employees",
        on_delete=models.SET_NULL,
    )
    role = models.ForeignKey(
        Role,
        null=True,
        blank=True,
        related_name="employees",
        on_delete=models.SET_NULL,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    start_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "employee_number"],
                name="uniq_employee_org_number",
            ),
        ]

    def __str__(self):
        return f"{self.employee_number} {self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

