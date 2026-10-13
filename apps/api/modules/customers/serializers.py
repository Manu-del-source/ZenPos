from rest_framework import serializers

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    """A customer as the client sees them.

    ``organization`` is read-only: it is stamped from the caller, never accepted
    from the request body.

    The points balance is not a column on the customer: it is the account
    maintained by the loyalty ledger (ADR-0021), exposed read-only from the
    model property so the POS gets the balance with the customer.
    """

    points_balance = serializers.IntegerField(read_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "organization",
            "name",
            "phone",
            "points_balance",
            "created_at",
        ]
        read_only_fields = ["organization"]

    def validate_phone(self, phone):
        """One live customer per phone number per organization.

        The database constraint says the same thing, but answered with a 400
        that names the problem rather than an IntegrityError at save time —
        and scoped to the caller's tenant, where the same person may well hold
        the same number at a different shop.
        """
        organization = self.context["request"].user.organization
        if organization is None:
            return phone
        queryset = Customer.objects.filter(organization=organization, phone=phone)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A customer with this phone number already exists in your organization."
            )
        return phone
