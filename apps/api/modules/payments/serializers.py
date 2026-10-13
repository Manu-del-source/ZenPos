from decimal import Decimal

from rest_framework import serializers

from modules.core.serializers import OrganizationScopedSerializerMixin
from modules.sales.models import Sale

from .models import Payment, PaymentAttempt
from .services import outstanding_for


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

    organization_bound_fields = ()

    sale = serializers.PrimaryKeyRelatedField(queryset=Sale.objects.all())
    method = serializers.ChoiceField(choices=Payment.Method.choices)
    phone = serializers.RegexField(
        regex=r"^0(1|7)\d{8}$",
        required=False,
        allow_blank=False,
        help_text="Safaricom number, e.g. 0722000000. Required for MPESA.",
    )
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        help_text=(
            "Cash legs only: how much of the outstanding balance this leg "
            "settles. Omit it to settle the whole remainder in cash. An "
            "M-Pesa leg is always charged the outstanding balance — the "
            "customer's phone is asked for what is left, not a client figure."
        ),
    )

    def validate_sale(self, sale):
        caller = self.request_user
        if caller is not None and caller.is_authenticated and not caller.is_superuser:
            if sale.organization_id != caller.organization_id:
                raise serializers.ValidationError(
                    "That record belongs to a different organization."
                )

            # The sale's branch must be one the caller is posted to, exactly as
            # the sales endpoint requires: paying another shop's sale would let
            # a cashier settle money they can neither see nor reconcile. A sale
            # with no branch at all (written before branches were recorded) is
            # not another shop's, so it stays payable.
            allowed = set(caller.branch_access.values_list("branch_id", flat=True))
            if allowed and sale.branch_id is not None and sale.branch_id not in allowed:
                raise serializers.ValidationError(
                    "That sale belongs to a branch you are not posted to."
                )

            if sale.status == Sale.Status.VOIDED:
                raise serializers.ValidationError("This sale has been voided.")

        return sale

    def validate(self, attrs):
        attrs = super().validate(attrs)
        method = attrs["method"]

        if method == Payment.Method.MPESA and not attrs.get("phone"):
            raise serializers.ValidationError(
                {"phone": "A customer phone number is required for an M-Pesa payment."}
            )
        if method == Payment.Method.CASH and attrs.get("phone"):
            raise serializers.ValidationError(
                {"phone": "A cash payment cannot have a phone number."}
            )

        sale = attrs["sale"]

        if attrs.get("amount") is not None and method != Payment.Method.CASH:
            raise serializers.ValidationError(
                {
                    "amount": (
                        "Only a cash leg takes an explicit amount; the M-Pesa "
                        "leg is charged the outstanding balance."
                    )
                }
            )

        # A sale is paid when its completed payments sum to the total; PENDING
        # legs count as unpaid — the money is not in yet.
        outstanding = outstanding_for(sale)
        if outstanding <= 0:
            raise serializers.ValidationError(
                {"sale": "This sale is already fully paid."}
            )

        leg_amount = attrs.get("amount") or outstanding
        if leg_amount > outstanding:
            raise serializers.ValidationError(
                {
                    "amount": (
                        f"That amount exceeds the outstanding balance of "
                        f"{outstanding}."
                    )
                }
            )

        # A split is declared at sale time. A sale that is not a split keeps
        # the single-payment contract: one live payment at a time. A failed
        # attempt does not count as live — a retry or a cash fallback is
        # still possible after a refused STK push.
        live = [
            payment
            for payment in sale.payments.all()
            if payment.status in (Payment.Status.PENDING, Payment.Status.COMPLETED)
        ]
        if sale.payment_method != Sale.PaymentMethod.SPLIT and live:
            raise serializers.ValidationError(
                {
                    "sale": (
                        "This sale is not a split sale; it already has a "
                        "live payment. Void the sale to start again."
                    )
                }
            )
        if method == Payment.Method.MPESA and any(
            payment.method == Payment.Method.MPESA for payment in live
        ):
            raise serializers.ValidationError(
                {
                    "sale": "This sale already has an M-Pesa payment in flight or completed."
                }
            )

        return attrs

    def create(self, validated_data) -> Payment:
        """A payment leg: an explicit cash figure, or the outstanding balance.

        The amount comes from the sale's ledger, never from the client: this
        endpoint asks for what the sale still owes. A cash leg may settle part
        of it (a split); anything else settles the remainder. The view re-checks
        the balance under a sale lock before the row is written — validation
        here is the friendly fast path, the lock is the authority.
        """
        sale = validated_data["sale"]
        amount = validated_data.pop("amount", None)
        if amount is None:
            amount = outstanding_for(sale)
        return Payment.objects.create(
            sale=sale,
            method=validated_data["method"],
            amount=amount,
            status=validated_data.get("status", Payment.Status.PENDING),
            received_by=validated_data.get("received_by"),
        )
