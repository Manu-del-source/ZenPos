from rest_framework import serializers

from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import LoyaltyAccount, LoyaltyLedger, LoyaltyRule


class LoyaltyRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltyRule
        fields = ("id", "organization", "amount", "points", "is_active", "updated_at")
        read_only_fields = ("id", "organization", "updated_at")


class LoyaltyLedgerSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = LoyaltyLedger
        fields = (
            "id",
            "points",
            "action",
            "reference_type",
            "reference_id",
            "actor",
            "actor_name",
            "branch",
            "branch_name",
            "notes",
            "balance_after",
            "created_at",
        )
        read_only_fields = fields


class LoyaltyAccountSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    entries = LoyaltyLedgerSerializer(many=True, read_only=True)
    organization_bound_fields = ("customer",)

    class Meta:
        model = LoyaltyAccount
        fields = (
            "id",
            "organization",
            "customer",
            "customer_name",
            "customer_phone",
            "points_balance",
            "entries",
            "updated_at",
        )
        read_only_fields = fields


class LoyaltyAdjustSerializer(serializers.Serializer):
    customer = serializers.CharField(required=False)
    points = serializers.IntegerField()
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    action = serializers.ChoiceField(
        choices=["EARN", "REDEEM", "ADJUST"],
        default="ADJUST",
    )

    def validate_points(self, value):
        if value == 0:
            raise serializers.ValidationError("Points cannot be zero.")
        return value
