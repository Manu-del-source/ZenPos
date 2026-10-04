from rest_framework import serializers

from modules.core.serializers import OrganizationScopedSerializerMixin
from modules.sales.models import Sale

from .models import Payment, PaymentAttempt


class PaymentAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentAttempt
        fields = (
            "id",
            "attempt_number",
            "provider",
            "provider_amount",
            "status",
            "error",
            "created_at",
        )


class PaymentSerializer(serializers.ModelSerializer):
    """Read-only surface for payment status polling from the POS."""

    attempts = PaymentAttemptSerializer(many=True, read_only=True)
    sale_number = serializers.ReadOnlyField(source="sale.sale_number")

    class Meta:
        model = Payment
        fields = (
            "id",
            "sale",
            "sale_number",
            "method",
            "amount",
            "currency",
            "status",
            "provider_reference",
            "received_by",
            "attempts",
            "created_at",
        )
        read_only_fields = fields


class InitiatePaymentSerializer(OrganizationScopedSerializerMixin, serializers.Serializer):
    """Create a payment for an existing sale and start its provider exchange.

    The sale is the organization boundary: the caller's organization must own
    it, which is checked in ``validate_sale`` against the caller's tenant, so
    another shop's sale id is a validation error, not a payment.
    """

    organization_bound_fields = ("sale",)

    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    phone = serializers.RegexField(
        regex=r"^0(1|7)\d{8}$",
        required=False,
        allow_blank=False,
        help_text="Safaricom number, e.g. 0722000000. Required for MPESA.",
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)

        if attrs["method"] == Payment.Method.MPESA and not attrs.get("phone"):
            raise serializers.ValidationError(
                {"phone": "A customer phone number is required for an M-Pesa payment."}
            )
        if attrs["method"] == Payment.Method.CASH and attrs.get("phone"):
            raise serializers.ValidationError(
                {"phone": "A cash payment cannot have a phone number."}
            )

        sale = attrs["sale"]
        completed_methods = {
            Payment.Method.CASH,
            Payment.Method.MPESA,
        }
        already = [
            payment.method
            for payment in sale.payments.filter(status=Payment.Status.COMPLETED)
            if payment.method in completed_methods
        ]
        if already:
            raise serializers.ValidationError(
                {"sale": "This sale already has a completed payment."}
            )

        return attrs

    def create(self, validated_data) -> Payment:
        """A payment starts as the full sale total, PENDING.

        The amount comes from the sale, never the client: this endpoint asks a
        provider to collect what the sale cost, and the sale's total was
        computed server-side at creation (phase 5 workstream 1). Partial and
        split payments arrive with the phase-6 sales rebuild.
        """
        return Payment.objects.create(
            sale=validated_data["sale"],
            method=validated_data["method"],
            amount=validated_data["sale"].total_amount,
            status=validated_data.get("status", Payment.Status.PENDING),
            received_by=validated_data.get("received_by"),
        )
