from rest_framework.exceptions import PermissionDenied, ValidationError


class OrganizationScopedMixin:
    """Restrict a viewset's queryset to the requesting user's organization.

    This is the tenant boundary: it stops one shop's staff from reading another
    shop's data. It answers *which tenant*, never *what may this person do* —
    permissions are enforced separately by
    ``modules.accounts.permissions.HasPermission``.

    ``organization_field`` is a filter path, so a model that reaches its tenant
    through a relation can say so (``"product__organization"``).

    Platform staff (superusers) see every organization, which is what makes the
    Django admin and support work possible.
    """

    organization_field = "organization"

    def get_organization(self):
        """The caller's organization, or ``None`` for a platform account."""
        return getattr(self.request.user, "organization", None)

    def get_queryset(self):
        queryset = super().get_queryset()

        if getattr(self.request.user, "is_superuser", False):
            return queryset

        organization = self.get_organization()
        if organization is None:
            # A non-superuser with no organization has no tenant to scope to.
            # Fail closed rather than leaking every organization's rows.
            return queryset.none()

        return queryset.filter(**{self.organization_field: organization})

    def perform_create(self, serializer):
        """File new records under the caller's organization, never a client value.

        A nested filter path (``product__organization``) means the related
        object already owns the tenant, so there is nothing to stamp here; the
        serializer mixin validates that the related object is in the same
        organization.
        """
        field = self.organization_field
        if "__" in field:
            serializer.save()
            return

        organization = self.get_organization()
        if organization is None:
            # A platform account belongs to no tenant, so it has nothing to file
            # a record under. Refuse rather than writing a row with a null
            # organization, which no organization would ever see again. Creating
            # a tenant is an admin action, not an API one.
            raise ValidationError(
                {"detail": "You do not belong to an organization, so you cannot create this."}
            )

        serializer.save(**{field: organization})


class BranchScopedMixin(OrganizationScopedMixin):
    """Narrow a queryset to the branches the caller is posted to.

    This is the *where* half of authorization, kept separate from the *what*
    half on purpose: a manager may hold a MANAGER role organization-wide while
    only being posted to two branches.

    A user with no ``UserBranchAccess`` rows is treated as organization-wide
    (head office). A user with rows is restricted to them. Branch access is read
    through the reverse relation on the user, so this module stays below
    ``accounts`` in the dependency order.

    ``branch_field`` is a filter path on the model being scoped. The Branch
    model itself sets ``branch_field = "id"``.
    """

    branch_field = "branch"

    # Creating a record *in* an existing branch requires access to it. Opening a
    # brand-new branch is different — the access rows for it cannot exist yet —
    # so BranchViewSet turns this off and relies on ``branches.manage``.
    enforce_branch_access_on_create = True

    def accessible_branch_ids(self):
        """Branch ids the caller may operate in, or ``None`` for all of them."""
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return None

        ids = list(user.branch_access.values_list("branch_id", flat=True))
        return ids or None

    def assert_branch_access(self, branch_id):
        ids = self.accessible_branch_ids()
        if ids is not None and branch_id not in ids:
            raise PermissionDenied("You do not have access to that branch.")

    def get_queryset(self):
        queryset = super().get_queryset()

        ids = self.accessible_branch_ids()
        if ids is None:
            return queryset

        return queryset.filter(**{f"{self.branch_field}__in": ids})

    def perform_create(self, serializer):
        if self.enforce_branch_access_on_create and self.get_organization() is not None:
            branch = serializer.validated_data.get(self.branch_field)
            if branch is not None:
                self.assert_branch_access(branch.pk)

        super().perform_create(serializer)
