from django.db import transaction
from rest_framework import mixins, viewsets

from modules.core.audit import record_audit, snapshot

from .models import Organization
from .serializers import OrganizationSerializer


class OrganizationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """Read and update your own organization.

    Creating and deleting organizations is intentionally not exposed here: it is
    a platform-operator action, not something a shop's own staff should reach.
    Use the Django admin.

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
