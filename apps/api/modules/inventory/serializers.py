from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from modules.branches.models import Branch
from modules.catalog.models import Product
from modules.core.audit import record_audit, snapshot
from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import (
    InventoryMovement,
    StockAdjustment,
    StockCount,
    StockCountLine,
    StockTransfer,
    StockTransferLine,
)
from .services import ADJUSTMENT_TO_MOVEMENT, apply_stock_movement, post_stock_count


class StockAdjustmentSerializer(
    OrganizationScopedSerializerMixin, serializers.ModelSerializer
):
    # Without this, a user could move stock on another organization's product by
    # sending its id: the queryset scoping stops them reading it, not writing to it.
    organization_bound_fields = ("product",)

    product_name = serializers.ReadOnlyField(source="product.name")
    user_name = serializers.ReadOnlyField(source="user.username")

    class Meta:
        model = StockAdjustment
        fields = "__all__"
        read_only_fields = ("user",)

    @transaction.atomic
    def create(self, validated_data):
        """Record the adjustment and apply it to stock as one unit of work.

        The product row is locked for the duration so two concurrent
        adjustments cannot interleave and lose an update. The ledger row is
        written inside the same transaction: if the stock write fails, the
        record of the attempt fails with it.
        """
        request = self.context["request"]
        user = request.user
        product = Product.objects.select_for_update().get(pk=validated_data["product"].pk)
        quantity = validated_data["quantity"]
        adj_type = validated_data["type"]
        notes = validated_data.get("notes", "") or ""

        branch = getattr(user, "default_branch", None)
        if branch is None and getattr(user, "is_authenticated", False):
            posting = user.branch_access.select_related("branch").first()
            branch = posting.branch if posting is not None else None

        before = snapshot(product, ("stock_level",))
        apply_stock_movement(
            product=product,
            quantity=Decimal(quantity),
            movement_type=ADJUSTMENT_TO_MOVEMENT[adj_type],
            organization=product.organization,
            branch=branch,
            reference_type="adjustment",
            actor=user,
            notes=notes,
            allow_negative=True,
            request=request,
        )
        adjustment = StockAdjustment.objects.create(
            product=product,
            user=user,
            quantity=quantity,
            type=adj_type,
            notes=notes,
        )
        product.refresh_from_db()
        record_audit(
            action="stock.adjusted",
            entity_type="product",
            entity_id=product.pk,
            actor=user,
            request=request,
            branch=branch,
            before=before,
            after={"stock_level": product.stock_level},
        )
        return adjustment


class InventoryMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    actor_name = serializers.CharField(source="actor.username", read_only=True)

    class Meta:
        model = InventoryMovement
        fields = (
            "id",
            "organization",
            "branch",
            "branch_name",
            "product",
            "product_name",
            "quantity",
            "movement_type",
            "reference_type",
            "reference_id",
            "actor",
            "actor_name",
            "quantity_before",
            "quantity_after",
            "unit_cost",
            "notes",
            "created_at",
        )
        read_only_fields = fields


class StockTransferLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockTransferLine
        fields = (
            "id",
            "product",
            "product_name",
            "requested_quantity",
            "approved_quantity",
            "dispatched_quantity",
            "received_quantity",
        )
        read_only_fields = (
            "id",
            "product_name",
            "approved_quantity",
            "dispatched_quantity",
            "received_quantity",
        )

    def validate_requested_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value


class StockTransferSerializer(
    OrganizationScopedSerializerMixin, serializers.ModelSerializer
):
    lines = StockTransferLineSerializer(many=True, required=False)
    source_branch_name = serializers.CharField(source="source_branch.name", read_only=True)
    destination_branch_name = serializers.CharField(
        source="destination_branch.name", read_only=True
    )
    requested_by_name = serializers.CharField(source="requested_by.username", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.username", read_only=True)
    dispatched_by_name = serializers.CharField(
        source="dispatched_by.username", read_only=True
    )
    received_by_name = serializers.CharField(source="received_by.username", read_only=True)

    organization_bound_fields = ("source_branch", "destination_branch")

    class Meta:
        model = StockTransfer
        fields = (
            "id",
            "number",
            "organization",
            "source_branch",
            "source_branch_name",
            "destination_branch",
            "destination_branch_name",
            "status",
            "notes",
            "lines",
            "requested_by",
            "requested_by_name",
            "requested_at",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "dispatched_by",
            "dispatched_by_name",
            "dispatched_at",
            "received_by",
            "received_by_name",
            "received_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "number",
            "organization",
            "status",
            "requested_by",
            "requested_by_name",
            "requested_at",
            "approved_by",
            "approved_by_name",
            "approved_at",
            "dispatched_by",
            "dispatched_by_name",
            "dispatched_at",
            "received_by",
            "received_by_name",
            "received_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        source = attrs.get("source_branch") or getattr(self.instance, "source_branch", None)
        dest = attrs.get("destination_branch") or getattr(
            self.instance, "destination_branch", None
        )
        if source is not None and dest is not None and source.pk == dest.pk:
            raise serializers.ValidationError(
                {"destination_branch": "Source and destination must be different branches."}
            )
        return attrs

    def validate_lines(self, lines):
        if self.instance is not None and not self.instance.is_editable():
            raise serializers.ValidationError(
                "Line items can only be changed while the transfer is a draft."
            )
        user = self.request_user
        org_id = getattr(user, "organization_id", None)
        if org_id is not None and not getattr(user, "is_superuser", False):
            for index, line in enumerate(lines):
                product = line.get("product")
                if product is not None and (
                    product.organization_id != org_id or product.deleted_at is not None
                ):
                    raise serializers.ValidationError(
                        {
                            index: {
                                "product": "That product belongs to a different "
                                "organization or has been archived."
                            }
                        }
                    )
        return lines

    def create(self, validated_data):
        lines = validated_data.pop("lines", [])
        if not lines:
            raise serializers.ValidationError(
                {"lines": "A transfer needs at least one line."}
            )
        transfer = StockTransfer.objects.create(**validated_data)
        StockTransferLine.objects.bulk_create(
            [
                StockTransferLine(
                    transfer=transfer,
                    product=line["product"],
                    requested_quantity=line["requested_quantity"],
                )
                for line in lines
            ]
        )
        return transfer

    def update(self, instance, validated_data):
        if not instance.is_editable() and validated_data:
            raise serializers.ValidationError(
                {"detail": "Only draft transfers can be edited."}
            )
        lines = validated_data.pop("lines", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(
            update_fields=[*validated_data.keys(), "updated_at"]
            if validated_data
            else None
        )

        if lines is not None:
            instance.lines.all().delete()
            StockTransferLine.objects.bulk_create(
                [
                    StockTransferLine(
                        transfer=instance,
                        product=line["product"],
                        requested_quantity=line["requested_quantity"],
                    )
                    for line in lines
                ]
            )
        return instance


class StockCountLineSerializer(serializers.ModelSerializer):
    """A count line as the back office reads it.

    ``variance_cost`` is the variance valued at the product's *current* cost
    column: a convenience for sizing the hit (or windfall), not a second
    source of cost truth — the ledger keeps the per-movement costs.
    """

    product_name = serializers.CharField(source="product.name", read_only=True)
    variance_cost = serializers.SerializerMethodField()

    class Meta:
        model = StockCountLine
        fields = (
            "id",
            "product",
            "product_name",
            "book_quantity",
            "counted_quantity",
            "variance",
            "variance_cost",
        )
        read_only_fields = fields

    def get_variance_cost(self, obj):
        if obj.product is None or obj.variance == 0:
            return Decimal("0.00")
        return (obj.variance * obj.product.cost_price).quantize(Decimal("0.01"))


class StockCountReadSerializer(serializers.ModelSerializer):
    """The posted count: header plus every line, read-only.

    There is no update or delete anywhere in this module — a count is a fact
    with a correction attached, and correcting the correction is a new count.
    """

    branch_name = serializers.CharField(source="branch.name", read_only=True)
    counted_by_name = serializers.SerializerMethodField()
    lines = StockCountLineSerializer(many=True, read_only=True)

    class Meta:
        model = StockCount
        fields = (
            "id",
            "number",
            "branch",
            "branch_name",
            "counted_at",
            "counted_by",
            "counted_by_name",
            "notes",
            "lines",
            "created_at",
        )
        read_only_fields = fields

    def get_counted_by_name(self, obj):
        return obj.counted_by.get_username() if obj.counted_by_id else ""


class StockCountItemSerializer(serializers.Serializer):
    """One line of the count payload: what the shelf physically held."""

    product = serializers.PrimaryKeyRelatedField(queryset=Product.objects.all())
    counted_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0")
    )


class StockCountWriteSerializer(OrganizationScopedSerializerMixin, serializers.Serializer):
    """The count as the floor staff sends it: a branch and the shelf.

    No header fields are client-shaped. The organization comes from the
    branch (which is tenant-scoped and validated), the number is generated,
    the book quantities are read from the ledger, and the counted-by is the
    signed-in user — a client cannot claim a count for someone else.
    """

    organization_bound_fields = ("branch",)

    branch = serializers.PrimaryKeyRelatedField(queryset=Branch.objects.all())
    counts = StockCountItemSerializer(many=True, allow_empty=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        organization_id = getattr(self.request_user, "organization_id", None)
        if organization_id is not None and not getattr(
            self.request_user, "is_superuser", False
        ):
            for item in attrs["counts"]:
                if item["product"].organization_id != organization_id:
                    raise serializers.ValidationError(
                        {"counts": "That record belongs to a different organization."}
                    )
        seen = set()
        for item in attrs["counts"]:
            if item["product"].pk in seen:
                raise serializers.ValidationError(
                    {"counts": "The same product appears more than once in one count."}
                )
            seen.add(item["product"].pk)
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        branch = validated_data["branch"]
        return post_stock_count(
            organization=branch.organization,
            branch=branch,
            counts=[
                (item["product"], item["counted_quantity"])
                for item in validated_data["counts"]
            ],
            actor=getattr(request, "user", None),
            request=request,
            notes=validated_data.get("notes", ""),
        )

    def to_representation(self, instance):
        """The posted count speaks in the read shape: lines, not payload."""
        return StockCountReadSerializer(instance, context=self.context).data
