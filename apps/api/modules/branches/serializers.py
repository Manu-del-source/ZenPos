from decimal import Decimal

from rest_framework import serializers

from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import Branch, CashMovement, CashSession, Till


class BranchSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, format="hex_verbose")
    organization = serializers.SerializerMethodField()
    organization_name = serializers.ReadOnlyField(source="organization.name")
    manager_name = serializers.SerializerMethodField()

    def get_manager_name(self, obj):
        if obj.manager_id is None:
            return None
        return obj.manager.get_username()

    def get_organization(self, obj):
        return str(obj.organization_id)

    def validate_code(self, value):
        request = self.context.get("request")
        organization_id = getattr(getattr(request, "user", None), "organization_id", None)
        queryset = Branch.objects.filter(organization_id=organization_id, code=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A branch with this code already exists in your organization."
            )
        return value

    class Meta:
        model = Branch
        fields = (
            "id",
            "organization",
            "organization_name",
            "name",
            "code",
            "address",
            "phone",
            "timezone",
            "manager",
            "manager_name",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")


class TillSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    organization_bound_fields = ("branch",)

    branch_name = serializers.ReadOnlyField(source="branch.name")
    organization_name = serializers.ReadOnlyField(source="organization.name")
    open_session = serializers.SerializerMethodField()

    def get_open_session(self, obj):
        session = (
            obj.sessions.filter(status=CashSession.Status.OPEN)
            .select_related("opened_by")
            .first()
        )
        if session is None:
            return None
        return {
            "id": str(session.pk),
            "status": session.status,
            "opening_cash": str(session.opening_cash),
            "opened_by": session.opened_by.get_username(),
            "opened_at": session.created_at,
        }

    def validate(self, attrs):
        # The super call runs the organization-bound checks: without it a
        # manager could attach another tenant's branch to one of their tills.
        attrs = super().validate(attrs)
        # Names are unique per branch (the database constraint), so the check
        # is scoped to the branch being written, not the whole organization.
        branch = attrs.get("branch") or getattr(self.instance, "branch", None)
        name = attrs.get("name", getattr(self.instance, "name", None))
        if branch is not None and name:
            queryset = Till.objects.filter(branch=branch, name=name)
            if self.instance is not None:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise serializers.ValidationError(
                    {"name": "A till with this name already exists in this branch."}
                )
        return attrs

    class Meta:
        model = Till
        fields = (
            "id",
            "organization",
            "organization_name",
            "branch",
            "branch_name",
            "name",
            "is_active",
            "open_session",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")


class OpenCashSessionSerializer(serializers.Serializer):
    opening_cash = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        help_text="The float counted into the drawer at the start of the shift.",
    )
    till = serializers.PrimaryKeyRelatedField(queryset=Till.objects.all())


class CashSessionSerializer(serializers.ModelSerializer):
    till_name = serializers.ReadOnlyField(source="till.name")
    branch_name = serializers.ReadOnlyField(source="branch.name")
    opened_by_name = serializers.ReadOnlyField(source="opened_by.username")
    closed_by_name = serializers.ReadOnlyField(source="closed_by.username")
    reviewed_by_name = serializers.ReadOnlyField(source="reviewed_by.username")

    class Meta:
        model = CashSession
        fields = (
            "id",
            "till",
            "till_name",
            "branch",
            "branch_name",
            "opened_by",
            "opened_by_name",
            "status",
            "opening_cash",
            "counted_cash",
            "expected_cash",
            "cash_variance",
            "close_notes",
            "closed_at",
            "closed_by_name",
            "reviewed_by_name",
            "reviewed_at",
            "review_notes",
            "created_at",
        )
        read_only_fields = fields


class RecordCashMovementSerializer(serializers.Serializer):
    movement_type = serializers.ChoiceField(choices=CashMovement.Type.choices)
    source = serializers.ChoiceField(
        choices=(
            (CashMovement.Source.MANUAL, CashMovement.Source.MANUAL),
        ),
        default=CashMovement.Source.MANUAL,
        required=False,
        help_text="Sales and refunds write their own movements; the API accepts manual ones.",
    )
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Positive amount; direction comes from movement_type.",
    )
    reason = serializers.CharField(
        max_length=255, allow_blank=False, help_text="Required: who authorised this and why."
    )
    reference = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default=""
    )


class CloseCashSessionSerializer(serializers.Serializer):
    counted_cash = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0"),
        help_text="The physical count of the drawer at close.",
    )
    notes = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ReviewCashSessionSerializer(serializers.Serializer):
    notes = serializers.CharField(
        max_length=255,
        allow_blank=False,
        help_text="What the supervisor found and how the discrepancy is explained.",
    )
