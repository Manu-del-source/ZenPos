from django.db import transaction
from django.db.models import Q
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import OrganizationScopedMixin
from modules.core.models import AuditLog

from .models import Employee, Permission, Role, User, UserBranchAccess, UserRole
from .serializers import (
    AuditLogSerializer,
    BranchAccessAssignmentSerializer,
    EmployeeSerializer,
    PermissionSerializer,
    RoleAssignmentSerializer,
    RoleSerializer,
    RoleWriteSerializer,
    SetPasswordSerializer,
    SetRolePermissionsSerializer,
    UserSerializer,
    UserWriteSerializer,
)

# Columns safe to copy into an audit row for a role.
ROLE_FIELDS = ("name", "description", "is_system", "organization")


class LoginRateThrottle(AnonRateThrottle):
    """Rate-limit credential attempts per client address.

    The rate lives in ``REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login"]``. This
    is the only thing standing between a weak cashier password and an offline
    guessing run, so it is applied to the login view rather than left configured
    and unused.
    """

    scope = "login"


class RefreshRateThrottle(AnonRateThrottle):
    """Refresh tokens are long-lived; minting them is throttled too."""

    scope = "refresh"


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginRateThrottle]


class RefreshView(TokenRefreshView):
    throttle_classes = [RefreshRateThrottle]


class LogoutView(APIView):
    """End a session by blacklisting the caller's refresh token.

    Clearing ``localStorage`` on the client does not revoke anything: the
    refresh token stays valid until it expires, which is exactly what a stolen
    token needs. Blacklisting it here is what actually ends the session.

    A token that is expired, malformed, or belongs to somebody else is ignored
    rather than reported: the first two are already useless, and telling a
    caller that another user's token is theirs to revoke would be a way to
    revoke strangers' sessions. Access tokens are short-lived by design, so a
    signed-out device cannot outlive its access token by much.
    """

    throttle_classes = [RefreshRateThrottle]

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                token = RefreshToken(refresh)
            except TokenError:
                token = None

            if token is not None and str(token.get("user_id")) == str(request.user.pk):
                try:
                    token.blacklist()
                except AttributeError:
                    # The blacklist app is not installed; the token simply
                    # expires on its own terms.
                    pass

        record_audit(
            action="auth.logout",
            entity_type="user",
            entity_id=request.user.pk,
            actor=request.user,
            request=request,
        )
        return Response({"detail": "Signed out."}, status=status.HTTP_200_OK)


class MeView(generics.RetrieveAPIView):
    """The authenticated user, with their roles, permissions and branch access.

    Clients read role, permission and branch from here on each load rather than
    trusting a copy cached in browser storage.
    """

    serializer_class = UserSerializer

    def get_queryset(self):
        return (
            User.objects.filter(pk=self.request.user.pk)
            .select_related("organization", "default_branch")
            .prefetch_related("user_roles__role__permissions", "branch_access")
        )

    def get_object(self):
        return self.get_queryset().get()


class RoleViewSet(viewsets.ModelViewSet):
    """The roles available to the requesting user.

    Reads are open to any authenticated user, because a client cannot render a
    staff form without knowing which roles exist. Every write requires
    ``users.manage``.
    """

    required_permissions_by_action = {
        "create": ("users.manage",),
        "update": ("users.manage",),
        "partial_update": ("users.manage",),
        "destroy": ("users.manage",),
        "set_permissions": ("users.manage",),
    }

    def get_queryset(self):
        return Role.objects.visible_to(self.request.user).prefetch_related("permissions")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return RoleWriteSerializer
        return RoleSerializer

    def perform_create(self, serializer):
        organization = getattr(self.request.user, "organization", None)
        if organization is None:
            raise ValidationError(
                {"detail": "You do not belong to an organization, so you cannot create roles."}
            )
        # New roles always belong to the caller's organization and are never
        # system roles: a client must not be able to mint a role shared by every
        # tenant.
        with transaction.atomic():
            serializer.save(organization=organization, is_system=False)
            record_audit(
                action="role.created",
                entity_type="role",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                after=snapshot(serializer.instance, ROLE_FIELDS),
            )

    def perform_update(self, serializer):
        if serializer.instance.is_system:
            raise PermissionDenied(
                "System roles are shared by every organization and cannot be edited."
            )
        with transaction.atomic():
            before = snapshot(serializer.instance, ROLE_FIELDS)
            serializer.save()
            record_audit(
                action="role.updated",
                entity_type="role",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                before=before,
                after=snapshot(serializer.instance, ROLE_FIELDS),
            )

    def perform_destroy(self, instance):
        if instance.is_system:
            raise PermissionDenied("System roles cannot be deleted.")
        if UserRole.objects.filter(role=instance).exists():
            # Deleting the role would cascade the grants away silently, which is
            # a privilege change nobody asked for and no one can audit.
            raise ValidationError(
                {"detail": "This role is still assigned to users. Revoke it first."}
            )
        with transaction.atomic():
            # The row is written before the delete, inside the same transaction:
            # afterwards there would be no instance to describe.
            record_audit(
                action="role.deleted",
                entity_type="role",
                entity_id=instance.pk,
                actor=self.request.user,
                request=self.request,
                before=snapshot(instance, ROLE_FIELDS),
            )
            instance.delete()

    @action(detail=True, methods=["post"], url_path="set-permissions")
    def set_permissions(self, request, pk=None):
        """Replace the role's permission set. Codes are validated, never assumed."""
        role = self.get_object()
        if role.is_system:
            raise PermissionDenied(
                "System roles are shared by every organization and cannot be edited."
            )

        payload = SetRolePermissionsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        with transaction.atomic():
            before_codes = sorted(role.permissions.values_list("code", flat=True))
            role.permissions.set(
                Permission.objects.filter(code__in=payload.validated_data["permission_codes"])
            )
            after_codes = sorted(role.permissions.values_list("code", flat=True))
            # This is the single most security-relevant event in the system: a
            # change here silently widens or narrows what a holder can do.
            record_audit(
                action="role.permissions_changed",
                entity_type="role",
                entity_id=role.pk,
                actor=request.user,
                request=request,
                before={"permission_codes": before_codes},
                after={"permission_codes": after_codes},
            )

        return Response(RoleSerializer(role, context=self.get_serializer_context()).data)


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """The global permission catalogue. Not organization-specific.

    Read-only: permissions are the vocabulary authorization is written against,
    and are seeded by migration. Applications are written against codes, so
    adding a permission without adding the code that checks it would grant
    nothing.
    """

    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """The audit log, readable only with ``audit.view``.

    Scoping is built by hand rather than through ``OrganizationScopedMixin``:
    rows have no organization of their own — the actor's organization covers
    them, and failed-login rows have no actor at all, with the tenant
    resolved through the attempted username instead. Both kinds must be
    visible to the organization that owns them, and no others.
    """

    required_permissions = ("audit.view",)
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("actor", "branch")

        if getattr(self.request.user, "is_superuser", False):
            return queryset

        organization_id = getattr(self.request.user, "organization_id", None)
        if organization_id is None:
            return queryset.none()

        usernames = list(
            User.objects.filter(organization_id=organization_id).values_list(
                "username", flat=True
            )
        )
        return queryset.filter(
            Q(actor__organization_id=organization_id)
            | Q(actor__isnull=True, attempted_username__in=usernames)
        )


class UserViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Staff accounts within the caller's organization.

    Every action requires ``users.manage``. The queryset is organization-scoped,
    so another organization's staff id is a 404 rather than a 403, and no path
    here accepts an organization from the client.
    """

    required_permissions = ("users.manage",)
    queryset = User.objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("organization", "default_branch")
            .prefetch_related("user_roles__role__permissions", "branch_access")
        )

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return UserWriteSerializer
        return UserSerializer

    def _ensure_manageable(self, target):
        """Refuse to touch accounts this API does not own."""
        if getattr(target, "is_superuser", False) and not getattr(
            self.request.user, "is_superuser", False
        ):
            raise PermissionDenied("Platform administrator accounts are managed outside the API.")

    def _refuse_self_privilege_change(self, target):
        """A manager must not be able to widen their own access."""
        if target.pk == self.request.user.pk:
            raise PermissionDenied("You cannot change your own access.")

    def _serialize_fresh(self, user):
        """Re-read the user, then serialize them.

        The grants were just replaced through the ``UserRole`` and
        ``UserBranchAccess`` managers rather than through this instance's reverse
        relations, so the instance's prefetched cache still holds the *previous*
        roles and postings. Re-reading is cheaper than reasoning about which
        cache a given write path invalidates.
        """
        refreshed = self.get_queryset().get(pk=user.pk)
        return Response(UserSerializer(refreshed, context=self.get_serializer_context()).data)

    def perform_update(self, serializer):
        self._ensure_manageable(serializer.instance)

        if (
            serializer.instance.pk == self.request.user.pk
            and serializer.validated_data.get("is_active") is False
        ):
            # Locking yourself out of the only account that can let you back in
            # is not a recoverable mistake.
            raise ValidationError({"is_active": "You cannot deactivate your own account."})

        serializer.save()

    def destroy(self, request, *args, **kwargs):
        """Refuse deletion: a staff account owns sales and adjustments forever.

        Deactivate with ``PATCH {"is_active": false}`` instead, so history keeps
        its author.
        """
        raise MethodNotAllowed(
            "DELETE", detail="Staff accounts are deactivated, not deleted."
        )

    @action(detail=True, methods=["post"], url_path="set-roles")
    def set_roles(self, request, pk=None):
        """Replace the user's role grants.

        Replacement, not append: a role omitted from the request is revoked. A
        grant with a branch applies only there; without one, it applies wherever
        the user can work.
        """
        user = self.get_object()
        self._ensure_manageable(user)
        self._refuse_self_privilege_change(user)

        payload = RoleAssignmentSerializer(data=request.data, context={"request": request})
        payload.is_valid(raise_exception=True)

        def assignments():
            """The current grants as compact, JSON-safe strings."""
            return sorted(
                f"{name}@{branch_id or 'org-wide'}"
                for name, branch_id in UserRole.objects.filter(user=user).values_list(
                    "role__name", "branch_id"
                )
            )

        with transaction.atomic():
            before = assignments()
            UserRole.objects.filter(user=user).delete()
            UserRole.objects.bulk_create(
                UserRole(user=user, role=grant["role"], branch_id=grant["branch_id"])
                for grant in payload.validated_data["roles"]
            )
            record_audit(
                action="user.roles_replaced",
                entity_type="user",
                entity_id=user.pk,
                actor=request.user,
                request=request,
                before={"roles": before},
                after={"roles": assignments()},
            )

        return self._serialize_fresh(user)

    @action(detail=True, methods=["post"], url_path="set-branch-access")
    def set_branch_access(self, request, pk=None):
        """Replace the branches the user is posted to.

        An empty list makes the user organization-wide (head office), which is
        how branch narrowing is lifted.
        """
        user = self.get_object()
        self._ensure_manageable(user)
        self._refuse_self_privilege_change(user)

        payload = BranchAccessAssignmentSerializer(data=request.data, context={"request": request})
        payload.is_valid(raise_exception=True)

        entries = payload.validated_data["branches"]

        def postings():
            """The current postings as compact, JSON-safe strings."""
            return sorted(
                f"{branch_id}{':default' if is_default else ''}"
                for branch_id, is_default in UserBranchAccess.objects.filter(
                    user=user
                ).values_list("branch_id", "is_default")
            )

        with transaction.atomic():
            before = postings()
            UserBranchAccess.objects.filter(user=user).delete()
            UserBranchAccess.objects.bulk_create(
                UserBranchAccess(
                    user=user, branch_id=entry["branch"], is_default=entry["is_default"]
                )
                for entry in entries
            )

            # default_branch is the branch the POS preselects. Keep it in step
            # with the postings rather than letting it point at a stale choice.
            default_branch_id = next(
                (entry["branch"] for entry in entries if entry["is_default"]), None
            )
            if default_branch_id is not None:
                user.default_branch_id = default_branch_id
                user.save(update_fields=["default_branch", "updated_at"])

            record_audit(
                action="user.branch_access_replaced",
                entity_type="user",
                entity_id=user.pk,
                actor=request.user,
                request=request,
                before={"branches": before},
                after={"branches": postings()},
            )

        return self._serialize_fresh(user)

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        """Set a staff member's password without the old one.

        This is the "manager resets a cashier's password" path, which is why it
        is behind ``users.manage`` and requires no old password. Outstanding
        refresh tokens are blacklisted so a reset ends existing sessions.
        """
        user = self.get_object()
        self._ensure_manageable(user)

        payload = SetPasswordSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        with transaction.atomic():
            user.set_password(payload.validated_data["password"])
            user.save(update_fields=["password", "updated_at"])
            for token in OutstandingToken.objects.filter(user=user):
                BlacklistedToken.objects.get_or_create(token=token)
            # Records *that* the password changed — never the secret or its hash.
            record_audit(
                action="user.password_reset",
                entity_type="user",
                entity_id=user.pk,
                actor=request.user,
                request=request,
            )

        return Response({"detail": "Password updated."}, status=status.HTTP_200_OK)


def _next_employee_number(organization) -> str:
    last = (
        Employee.all_objects.filter(organization=organization)
        .order_by("-employee_number")
        .values_list("employee_number", flat=True)
        .first()
    )
    if last is None or not last.startswith("EMP-"):
        return "EMP-000001"
    try:
        return f"EMP-{int(last[4:]) + 1:06d}"
    except ValueError:
        return "EMP-000001"


class EmployeeViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Employee.objects.select_related("branch", "role", "user", "organization")
    serializer_class = EmployeeSerializer

    required_permissions = ("users.manage",)

    def get_queryset(self):
        queryset = super().get_queryset()
        params = self.request.query_params
        status_param = params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())
        branch = params.get("branch")
        if branch:
            queryset = queryset.filter(branch_id=branch)
        search = params.get("search")
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(employee_number__icontains=search)
                | Q(phone__icontains=search)
            )
        return queryset

    def perform_create(self, serializer):
        with transaction.atomic():
            organization = self.get_organization()
            serializer.save(
                organization=organization,
                employee_number=_next_employee_number(organization),
            )
            emp = serializer.instance
            record_audit(
                action="staff.created",
                entity_type="employee",
                entity_id=emp.pk,
                actor=self.request.user,
                request=self.request,
                branch=emp.branch,
                after=snapshot(emp),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            action = (
                "staff.status_changed"
                if before.get("status") != serializer.instance.status
                else "staff.updated"
            )
            record_audit(
                action=action,
                entity_type="employee",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                branch=serializer.instance.branch,
                before=before,
                after=snapshot(serializer.instance),
            )

    def destroy(self, request, *args, **kwargs):
        emp = self.get_object()
        with transaction.atomic():
            before = snapshot(emp)
            emp.status = Employee.Status.TERMINATED
            emp.soft_delete()
            record_audit(
                action="staff.status_changed",
                entity_type="employee",
                entity_id=emp.pk,
                actor=request.user,
                request=request,
                branch=emp.branch,
                before=before,
                after={"status": emp.status, "deleted_at": str(emp.deleted_at)},
            )
        return Response(EmployeeSerializer(emp, context={"request": request}).data)

