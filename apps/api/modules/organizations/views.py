from django.db import transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from modules.core.audit import record_audit, snapshot

from .models import Organization
from .serializers import OrganizationSerializer, PlatformOrganizationOnboardSerializer
from .services import onboard_organization


class OrganizationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Read and update your own organization.

    Creating and closing tenants is intentionally not exposed here: it is a
    platform-operator action on the ``/api/v2/platform/organizations/``
    surface (see ``PlatformOrganizationViewSet``), and ``is_active`` is not
    tenant-writable, so a shop cannot suspend — or re-open — itself.

    Reading is open to any authenticated user, because the client needs the
    currency and timezone to render money and dates correctly. Changing the
    organization requires ``settings.manage``.
    """

    serializer_class = OrganizationSerializer

    required_permissions_by_action = {
        "update": ("settings.manage",),
        "partial_update": ("settings.manage",),
    }

    def perform_update(self, serializer):
        # An organization profile change (name, currency, timezone) affects how
        # every branch renders money and dates, so it is audited.
        with transaction.atomic():
            before = snapshot(serializer.instance)
            serializer.save()
            record_audit(
                action="organization.updated",
                entity_type="organization",
                entity_id=serializer.instance.pk,
                actor=self.request.user,
                request=self.request,
                before=before,
                after=snapshot(serializer.instance),
            )

    def get_queryset(self):
        user = self.request.user
        if getattr(user, "is_superuser", False):
            return Organization.objects.all()

        organization_id = getattr(user, "organization_id", None)
        if organization_id is None:
            return Organization.objects.none()

        return Organization.objects.filter(pk=organization_id)


class IsPlatformStaff(BasePermission):
    """Platform endpoints answer to superusers only.

    The tenant role vocabulary decides what a user may do *inside* a tenant;
    this decides who may act on tenants themselves. There is deliberately no
    API path that grants superuser, so this cannot be self-granted.
    """

    message = "Platform staff only."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


class PlatformOrganizationViewSet(mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Opening and closing tenants: a platform-operator action (ADR-0022).

    Onboarding creates the organization, its first branch and its first
    administrator as one audited fact. Suspend and activate flip the tenant
    switch that ``HasPermission`` and the token views enforce at login,
    refresh and every API call.
    """

    permission_classes = (IsPlatformStaff,)
    queryset = Organization.objects.all()
    serializer_class = PlatformOrganizationOnboardSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = onboard_organization(
            **serializer.validated_data, actor=request.user, request=request
        )
        return Response(
            OrganizationSerializer(organization, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    def _flip(self, request, is_active, audit_action):
        organization = self.get_object()
        if organization.is_active == is_active:
            # Flipping a switch that is already in the wanted position would
            # only add an audit row for nothing.
            state = "active" if is_active else "suspended"
            raise ValidationError({"detail": f"Organization is already {state}."})

        with transaction.atomic():
            before = snapshot(organization)
            organization.is_active = is_active
            organization.save(update_fields=["is_active", "updated_at"])
            record_audit(
                action=audit_action,
                entity_type="organization",
                entity_id=organization.pk,
                actor=request.user,
                request=request,
                before=before,
                after=snapshot(organization),
            )
        return Response(
            OrganizationSerializer(organization, context=self.get_serializer_context()).data
        )

    @action(detail=True, methods=["post"])
    def suspend(self, request, *args, **kwargs):
        return self._flip(request, is_active=False, audit_action="organization.suspended")

    @action(detail=True, methods=["post"])
    def activate(self, request, *args, **kwargs):
        return self._flip(request, is_active=True, audit_action="organization.activated")
