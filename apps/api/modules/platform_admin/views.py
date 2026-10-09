"""Platform Super Admin API (``/api/v2/platform/``).

Every view here requires ``IsPlatformAdmin`` (an active superuser). Every state
change is audited inside the transaction that performs it. Nothing here accepts
or returns a password hash, token, or other secret except the one-time invite
token, which is shown once to the platform admin who issued it.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from modules.accounts.models import Role, UserRole
from modules.branches.models import Branch
from modules.core.audit import record_audit, snapshot
from modules.core.models import AuditLog
from modules.organizations.models import Organization

from .permissions import IsPlatformAdmin
from .serializers import (
    AcceptInviteSerializer,
    OwnerInviteSerializer,
    PlatformAuditLogSerializer,
    PlatformBranchSerializer,
    PlatformOrganizationSerializer,
    PlatformUserSerializer,
)

User = get_user_model()

USER_AUDIT_FIELDS = ["username", "email", "organization_id", "is_active", "is_superuser"]


def _truthy(value):
    return str(value).lower() in {"1", "true", "yes"}


class PlatformViewMixin:
    permission_classes = [IsPlatformAdmin]


class PlatformOverviewView(PlatformViewMixin, APIView):
    """Counts straight from the database; nothing here is estimated."""

    def get(self, request):
        since = timezone.now() - timedelta(hours=24)
        return Response(
            {
                "organizations": {
                    "total": Organization.objects.count(),
                    "active": Organization.objects.filter(is_active=True).count(),
                },
                "branches": {
                    "total": Branch.objects.count(),
                    "active": Branch.objects.filter(is_active=True).count(),
                },
                "users": {
                    "total": User.objects.count(),
                    "active": User.objects.filter(is_active=True).count(),
                    "platform_admins": User.objects.filter(
                        is_superuser=True, is_active=True
                    ).count(),
                },
                "audit": {
                    "events_24h": AuditLog.objects.filter(created_at__gte=since).count(),
                    "failed_logins_24h": AuditLog.objects.filter(
                        action="auth.login_failed", created_at__gte=since
                    ).count(),
                },
                "generated_at": timezone.now(),
            }
        )


class PlatformOrganizationViewSet(
    PlatformViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """No delete: an organization owns financial history. Deactivate instead."""

    serializer_class = PlatformOrganizationSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Organization.objects.annotate(
            branch_count=Count("branches", distinct=True),
            user_count=Count("users", distinct=True),
        ).order_by("name")
        params = self.request.query_params
        search = params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(slug__icontains=search))
        if params.get("is_active") in {"true", "false"}:
            qs = qs.filter(is_active=_truthy(params["is_active"]))
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            org = serializer.save()
            record_audit(
                action="platform.organization_created",
                entity_type="organization",
                entity_id=org.pk,
                actor=self.request.user,
                request=self.request,
                after=snapshot(org),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            org = serializer.save()
            was, now = before["is_active"], org.is_active
            action_name = "platform.organization_updated"
            if was and not now:
                action_name = "platform.organization_deactivated"
            elif not was and now:
                action_name = "platform.organization_activated"
            record_audit(
                action=action_name,
                entity_type="organization",
                entity_id=org.pk,
                actor=self.request.user,
                request=self.request,
                before=before,
                after=snapshot(org),
            )


class PlatformBranchViewSet(
    PlatformViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PlatformBranchSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        qs = Branch.objects.select_related("organization").order_by("organization__name", "name")
        params = self.request.query_params
        if params.get("organization"):
            qs = qs.filter(organization_id=params["organization"])
        search = params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        if params.get("is_active") in {"true", "false"}:
            qs = qs.filter(is_active=_truthy(params["is_active"]))
        return qs

    def perform_create(self, serializer):
        with transaction.atomic():
            branch = serializer.save()
            record_audit(
                action="platform.branch_created",
                entity_type="branch",
                entity_id=branch.pk,
                actor=self.request.user,
                request=self.request,
                branch=branch,
                after=snapshot(branch),
            )

    def perform_update(self, serializer):
        with transaction.atomic():
            before = snapshot(serializer.instance)
            branch = serializer.save()
            name = "platform.branch_updated"
            if before["is_active"] and not branch.is_active:
                name = "platform.branch_deactivated"
            elif not before["is_active"] and branch.is_active:
                name = "platform.branch_activated"
            record_audit(
                action=name,
                entity_type="branch",
                entity_id=branch.pk,
                actor=self.request.user,
                request=self.request,
                branch=branch,
                before=before,
                after=snapshot(branch),
            )


class PlatformUserViewSet(
    PlatformViewMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = PlatformUserSerializer

    def get_queryset(self):
        qs = (
            User.objects.select_related("organization")
            .prefetch_related("user_roles__role")
            .order_by("username")
        )
        params = self.request.query_params
        if params.get("organization"):
            qs = qs.filter(organization_id=params["organization"])
        search = params.get("search")
        if search:
            qs = qs.filter(
                Q(username__icontains=search)
                | Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
            )
        if params.get("is_active") in {"true", "false"}:
            qs = qs.filter(is_active=_truthy(params["is_active"]))
        if params.get("platform_admin") in {"true", "false"}:
            qs = qs.filter(is_superuser=_truthy(params["platform_admin"]))
        return qs

    @action(detail=True, methods=["post"], url_path="set-platform-admin")
    def set_platform_admin(self, request, pk=None):
        """Grant or revoke platform authority. Only an existing platform admin can."""
        target = self.get_object()
        value = request.data.get("is_platform_admin")
        if not isinstance(value, bool):
            raise ValidationError({"is_platform_admin": "Send true or false."})
        if target.pk == request.user.pk:
            raise PermissionDenied("You cannot change your own platform access.")
        with transaction.atomic():
            # Lock the superuser rows so two admins cannot each revoke the other
            # and leave the platform with nobody who can administer it.
            list(User.objects.select_for_update().filter(is_superuser=True))
            if not value and target.is_superuser:
                remaining = User.objects.filter(is_superuser=True, is_active=True).exclude(
                    pk=target.pk
                )
                if not remaining.exists():
                    raise ValidationError(
                        {"detail": "At least one active platform administrator must remain."}
                    )
            before = snapshot(target, USER_AUDIT_FIELDS)
            if value and not target.is_active:
                raise ValidationError({"detail": "Activate the account first."})
            target.is_superuser = value
            target.is_staff = value  # keeps Django's technical admin in step
            target.save(update_fields=["is_superuser", "is_staff", "updated_at"])
            record_audit(
                action="platform.admin_granted" if value else "platform.admin_revoked",
                entity_type="user",
                entity_id=target.pk,
                actor=request.user,
                request=request,
                before=before,
                after=snapshot(target, USER_AUDIT_FIELDS),
            )
        return Response(self.get_serializer(self.get_object()).data)

    @action(detail=True, methods=["post"], url_path="set-active")
    def set_active(self, request, pk=None):
        target = self.get_object()
        value = request.data.get("is_active")
        if not isinstance(value, bool):
            raise ValidationError({"is_active": "Send true or false."})
        if target.pk == request.user.pk:
            raise PermissionDenied("You cannot change your own active status.")
        with transaction.atomic():
            if not value and target.is_superuser:
                others = User.objects.filter(is_superuser=True, is_active=True).exclude(
                    pk=target.pk
                )
                if not others.exists():
                    raise ValidationError(
                        {"detail": "At least one active platform administrator must remain."}
                    )
            before = snapshot(target, USER_AUDIT_FIELDS)
            target.is_active = value
            target.save(update_fields=["is_active", "updated_at"])
            record_audit(
                action="platform.user_activated" if value else "platform.user_deactivated",
                entity_type="user",
                entity_id=target.pk,
                actor=request.user,
                request=request,
                before=before,
                after=snapshot(target, USER_AUDIT_FIELDS),
            )
        return Response(self.get_serializer(self.get_object()).data)


class OwnerInviteView(PlatformViewMixin, APIView):
    """Create an organization owner with no usable password and issue a one-time invite.

    The owner sets their own password through ``/platform/invites/accept/``. The
    platform admin never sees or chooses it. The token is bound to the account's
    current password hash and ``last_login``, so it dies the moment it is used,
    and expires after ``PASSWORD_RESET_TIMEOUT``.
    """

    def post(self, request):
        serializer = OwnerInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        organization = data["organization"]
        if not organization.is_active:
            raise ValidationError({"organization": "That organization is deactivated."})
        admin_role = Role.objects.get(name="ADMIN", organization__isnull=True)
        with transaction.atomic():
            user = User(
                username=data["username"],
                email=data["email"],
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                organization=organization,
            )
            user.set_unusable_password()
            user.save()
            UserRole.objects.create(user=user, role=admin_role)
            record_audit(
                action="platform.owner_invited",
                entity_type="user",
                entity_id=user.pk,
                actor=request.user,
                request=request,
                after=snapshot(user, USER_AUDIT_FIELDS),
            )
        return Response(
            {
                "user": PlatformUserSerializer(user).data,
                "invite": {
                    "uid": urlsafe_base64_encode(force_bytes(user.pk)),
                    "token": default_token_generator.make_token(user),
                    "note": "Shown once. Send it to the owner over a private channel.",
                },
            },
            status=status.HTTP_201_CREATED,
        )


class InviteThrottle(AnonRateThrottle):
    rate = "10/min"


class AcceptInviteView(APIView):
    """Public by necessity (the invitee has no account access yet); throttled."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [InviteThrottle]

    def post(self, request):
        serializer = AcceptInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        invalid = ValidationError({"detail": "This invite link is invalid or has expired."})
        try:
            user = User.objects.get(pk=force_str(urlsafe_base64_decode(data["uid"])))
        except (User.DoesNotExist, DjangoValidationError, ValueError, TypeError, OverflowError):
            raise invalid from None
        if not user.is_active or not default_token_generator.check_token(user, data["token"]):
            raise invalid
        try:
            validate_password(data["password"], user)
        except DjangoValidationError as exc:
            raise ValidationError({"password": list(exc.messages)}) from None
        with transaction.atomic():
            user.set_password(data["password"])
            user.save(update_fields=["password", "updated_at"])
            record_audit(
                action="platform.invite_accepted",
                entity_type="user",
                entity_id=user.pk,
                actor=user,
                request=request,
            )
        return Response({"detail": "Password set. You can now sign in."})


class PlatformAuditLogViewSet(
    PlatformViewMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = PlatformAuditLogSerializer

    def get_queryset(self):
        qs = AuditLog.objects.select_related("actor", "actor__organization").order_by("-created_at")
        params = self.request.query_params
        if params.get("action"):
            qs = qs.filter(action__startswith=params["action"])
        if params.get("organization"):
            qs = qs.filter(actor__organization_id=params["organization"])
        if params.get("entity_type"):
            qs = qs.filter(entity_type=params["entity_type"])
        if params.get("date_from"):
            qs = qs.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            qs = qs.filter(created_at__date__lte=params["date_to"])
        search = params.get("search")
        if search:
            qs = qs.filter(
                Q(actor__username__icontains=search)
                | Q(attempted_username__icontains=search)
                | Q(action__icontains=search)
            )
        return qs


class PlatformHealthView(PlatformViewMixin, APIView):
    """Only signals the API can actually measure. Anything it cannot is omitted."""

    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_ok = False
        pending = None
        if db_ok:
            executor = MigrationExecutor(connection)
            pending = len(executor.migration_plan(executor.loader.graph.leaf_nodes()))
        latest = AuditLog.objects.order_by("-created_at").values_list("created_at", flat=True)[:1]
        return Response(
            {
                "database": "ok" if db_ok else "unavailable",
                "pending_migrations": pending,
                "debug_mode": bool(settings.DEBUG),
                "mpesa_callback_secret_configured": bool(
                    getattr(settings, "MPESA_CALLBACK_SECRET", "")
                ),
                "latest_audit_event_at": latest[0] if latest else None,
                "checked_at": timezone.now(),
            }
        )
