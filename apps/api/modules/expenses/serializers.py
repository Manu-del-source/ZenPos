from rest_framework import serializers

from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import Expense, ExpenseCategory
from .services import next_expense_number


class ExpenseCategorySerializer(serializers.ModelSerializer):
    organization_name = serializers.ReadOnlyField(source="organization.name")

    class Meta:
        model = ExpenseCategory
        fields = (
            "id",
            "organization",
            "organization_name",
            "name",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")

    def validate(self, attrs):
        # Names are unique per organization (the database constraint). Checking
        # here turns a collision into a 400 with a message instead of the
        # constraint raising a 500 mid-request.
        name = attrs.get("name")
        if name is None:
            return attrs
        organization = getattr(self.context["request"].user, "organization", None)
        queryset = ExpenseCategory.objects.filter(organization=organization, name=name)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                {"name": "A category with this name already exists."}
            )
        return attrs


class ExpenseSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    """Reads expose the full row; writes accept the facts, never the stamp.

    ``organization`` is stamped from the caller, ``created_by`` from the
    request, and ``expense_number`` generated server-side: a client that tried
    to send any of them would be overwriting the audit trail, so the fields
    are read-only on input and filled in ``create`` instead.
    """

    organization_bound_fields = ("branch", "category")

    branch_name = serializers.ReadOnlyField(source="branch.name")
    category_name = serializers.ReadOnlyField(source="category.name")
    organization_name = serializers.ReadOnlyField(source="organization.name")
    created_by_name = serializers.ReadOnlyField(source="created_by.get_username")
    is_reversal = serializers.ReadOnlyField()

    class Meta:
        model = Expense
        fields = (
            "id",
            "expense_number",
            "organization",
            "organization_name",
            "branch",
            "branch_name",
            "category",
            "category_name",
            "date",
            "amount",
            "reference",
            "notes",
            "created_by",
            "created_by_name",
            "reversal_of",
            "is_reversal",
            "created_at",
        )
        read_only_fields = (
            "id",
            "expense_number",
            "organization",
            "created_by",
            "reversal_of",
            "created_at",
        )

    def validate(self, attrs):
        # The super call runs the organization-bound checks: without it a
        # manager could attach another tenant's branch or category to an
        # expense and book this shop's spend against someone else's.
        attrs = super().validate(attrs)
        category = attrs.get("category")
        if category is not None and not category.is_active:
            raise serializers.ValidationError(
                {"category": "That category is no longer active."}
            )
        return attrs

    def create(self, validated_data):
        # Stamped server-side, like a sale's cashier: the actor and the number
        # are facts about the event, not client input.
        validated_data["created_by"] = self.context["request"].user
        validated_data["expense_number"] = next_expense_number()
        return super().create(validated_data)
