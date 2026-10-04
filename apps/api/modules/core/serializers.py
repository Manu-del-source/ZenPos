from rest_framework import serializers


class OrganizationScopedSerializerMixin:
    """Reject related objects that belong to a different organization.

    Queryset scoping stops a user *reading* another tenant's rows, but an
    unfiltered foreign key still lets them *attach* one: a cashier could create
    a product pointing at another organization's category, or a stock adjustment
    against another organization's product. The relation carries the tenant, so
    it has to be validated explicitly.

    List the fields to check in ``organization_bound_fields``. A platform
    superuser with no organization is not scoped and skips the check, matching
    ``OrganizationScopedMixin``.
    """

    organization_bound_fields: tuple[str, ...] = ()

    def validate(self, attrs):
        attrs = super().validate(attrs)

        organization_id = getattr(self.request_user, "organization_id", None)
        if organization_id is None or getattr(self.request_user, "is_superuser", False):
            return attrs

        for field in self.organization_bound_fields:
            related = attrs.get(field)
            if related is None:
                continue
            if getattr(related, "organization_id", None) != organization_id:
                raise serializers.ValidationError(
                    {field: "That record belongs to a different organization."}
                )

        return attrs

    @property
    def request_user(self):
        request = self.context.get("request")
        return getattr(request, "user", None)
