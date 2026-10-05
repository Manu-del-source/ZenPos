from rest_framework import serializers

from .models import Supplier


class SupplierSerializer(serializers.ModelSerializer):
    """A supplier as the client sees them.

    ``organization`` is read-only: it is stamped from the caller, never
    accepted from the request body. There are no related organization-scoped
    fields to validate — a supplier carries no foreign keys beyond its tenant —
    so the ``OrganizationScopedSerializerMixin`` cross-tenant check has nothing
    to guard here.
    """

    class Meta:
        model = Supplier
        fields = (
            "id",
            "organization",
            "name",
            "contact_name",
            "phone",
            "email",
            "address",
            "payment_terms",
            "status",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Supplier name is required.")
        return name

    def validate_status(self, value):
        if value not in Supplier.Status.values:
            raise serializers.ValidationError("Status must be ACTIVE or BLOCKED.")
        return value

    def validate(self, attrs):
        """Refuse a name that collides with a live supplier in the same organization.

        The ``(organization, name)`` unique constraint on live rows is the hard
        authority — this lookup only turns the common case into a clean 400
        instead of a 500 from the IntegrityError the constraint raises in a
        race the validation window missed. The match is case-insensitive, which
        is stricter than the constraint on purpose: two suppliers differing
        only in capitalisation is a data-entry accident, not a choice.
        """
        name = attrs.get("name")
        if name is None:
            return attrs

        user = getattr(self.context.get("request"), "user", None)
        organization_id = getattr(user, "organization_id", None)
        if organization_id is None or getattr(user, "is_superuser", False):
            return attrs

        queryset = Supplier.objects.filter(
            organization_id=organization_id,
            name__iexact=name.strip(),
            deleted_at__isnull=True,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {"name": "A supplier with this name already exists."}
            )
        return attrs
