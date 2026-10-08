from decimal import Decimal

from rest_framework import serializers

from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import GoodsReceivedLine, GoodsReceivedNote, PurchaseOrder, PurchaseOrderLine, Supplier


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


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True,
    )
    product_name = serializers.CharField(source="product.name", read_only=True)
    quantity_received = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )
    quantity_outstanding = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )

    class Meta:
        model = PurchaseOrderLine
        fields = (
            "id",
            "product",
            "product_name",
            "quantity",
            "quantity_received",
            "quantity_outstanding",
            "unit_cost",
            "line_total",
        )
        # unit_cost is optional on the wire: when omitted, create() defaults it
        # to the product's current cost price.
        extra_kwargs = {"unit_cost": {"required": False}}
        read_only_fields = (
            "id",
            "product_name",
            "quantity_received",
            "quantity_outstanding",
            "line_total",
        )

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value

    def validate_unit_cost(self, value):
        # None means "not supplied": create() and update() default it.
        if value is None or value >= 0:
            return value
        raise serializers.ValidationError("Unit cost cannot be negative.")


class PurchaseOrderSerializer(
    OrganizationScopedSerializerMixin, serializers.ModelSerializer
):
    """A purchase order and its lines, read and written as one document.

    The lines ride on the order when it is created or edited: a draft is one
    document in the user's head, not two rows to keep in step. The nested write
    replaces the whole line set on every edit — the UI sends what the draft
    now says; keeping per-line ids to diff against is API surface the first
    consumer does not need.

    Lines are only accepted while the order is DRAFT (enforced again in the
    view, which owns the instance's *current* status); the serializer refuses
    line edits on a non-draft regardless of what the client asked for.
    """

    lines = PurchaseOrderLineSerializer(many=True, required=False)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    total_cost = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    organization_bound_fields = ("branch", "supplier")

    # Products reach the tenant through the lines, which DRF's flat
    # ``organization_bound_fields`` cannot reach; they are checked here.
    class Meta:
        model = PurchaseOrder
        fields = (
            "id",
            "number",
            "organization",
            "branch",
            "branch_name",
            "supplier",
            "supplier_name",
            "status",
            "expected_date",
            "notes",
            "total_cost",
            "lines",
            "created_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "number",
            "organization",
            "status",
            "total_cost",
            "created_by",
            "approved_by",
            "approved_at",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        """Refuse a BLOCKED supplier on a new draft.

        Their history keeps its author; a new business day does not. Nothing
        here stops the *receiving* of an order already raised against them.
        """
        attrs = super().validate(attrs)
        supplier = attrs.get("supplier")
        if self.instance is None and supplier is not None:
            if (
                supplier.status == Supplier.Status.BLOCKED
                and not getattr(self.request_user, "is_superuser", False)
            ):
                raise serializers.ValidationError(
                    {"supplier": "That supplier is blocked. Unblock them first."}
                )
        return attrs

    def validate_lines(self, lines):
        if self.instance is not None and not self.instance.is_editable():
            raise serializers.ValidationError(
                "Line items can only be changed while the order is a draft."
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
        with_lines = bool(lines)
        if not with_lines:
            raise serializers.ValidationError(
                {"lines": "A purchase order needs at least one line."}
            )

        line_data = []
        for line in lines:
            unit_cost = line.get("unit_cost")
            if unit_cost is None:
                unit_cost = line["product"].cost_price
            line_data.append(
                {
                    "product": line["product"],
                    "quantity": line["quantity"],
                    "unit_cost": unit_cost,
                }
            )

        order = PurchaseOrder.objects.create(**validated_data)
        order.lines.bulk_create(
            PurchaseOrderLine(purchase_order=order, **data) for data in line_data
        )
        return order

    def update(self, instance, validated_data):
        # Draft-only editing is enforced in validate_lines for line changes;
        # header fields on a submitted order are refused here for symmetry.
        if not instance.is_editable() and validated_data:
            raise serializers.ValidationError(
                {"detail": "Only draft purchase orders can be edited."}
            )

        lines = validated_data.pop("lines", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data.keys(), "updated_at"])

        if lines is not None:
            instance.lines.all().delete()
            line_data = []
            for line in lines:
                unit_cost = line.get("unit_cost")
                if unit_cost is None:
                    unit_cost = line["product"].cost_price
                line_data.append(
                    PurchaseOrderLine(
                        purchase_order=instance,
                        product=line["product"],
                        quantity=line["quantity"],
                        unit_cost=unit_cost,
                    )
                )
            instance.lines.bulk_create(line_data)

        return instance


class GoodsReceivedLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    quantity_outstanding = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True
    )
    line_total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = GoodsReceivedLine
        fields = (
            "id",
            "purchase_order_line",
            "product",
            "product_name",
            "ordered_quantity",
            "previously_received",
            "quantity_outstanding",
            "quantity_received",
            "unit_cost",
            "line_total",
            "batch_number",
            "expiry_date",
        )
        read_only_fields = (
            "id",
            "product",
            "product_name",
            "ordered_quantity",
            "previously_received",
            "quantity_outstanding",
            "line_total",
        )
        extra_kwargs = {"unit_cost": {"required": False}}

    def validate_quantity_received(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity received must be greater than zero.")
        return value


class GoodsReceivedNoteSerializer(
    OrganizationScopedSerializerMixin, serializers.ModelSerializer
):
    lines = GoodsReceivedLineSerializer(many=True, required=False)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)
    purchase_order_number = serializers.CharField(
        source="purchase_order.number", read_only=True
    )
    received_by_name = serializers.CharField(
        source="received_by.username", read_only=True
    )
    posted_by_name = serializers.CharField(source="posted_by.username", read_only=True)
    total_cost = serializers.SerializerMethodField()

    organization_bound_fields = ("purchase_order",)

    class Meta:
        model = GoodsReceivedNote
        fields = (
            "id",
            "number",
            "organization",
            "branch",
            "branch_name",
            "supplier",
            "supplier_name",
            "purchase_order",
            "purchase_order_number",
            "delivery_note",
            "received_date",
            "status",
            "notes",
            "total_cost",
            "lines",
            "received_by",
            "received_by_name",
            "posted_by",
            "posted_by_name",
            "posted_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "number",
            "organization",
            "branch",
            "branch_name",
            "supplier",
            "supplier_name",
            "purchase_order_number",
            "status",
            "total_cost",
            "received_by",
            "received_by_name",
            "posted_by",
            "posted_by_name",
            "posted_at",
            "created_at",
            "updated_at",
        )

    def get_total_cost(self, obj):
        return sum(
            (line.quantity_received * line.unit_cost for line in obj.lines.all()),
            start=Decimal("0"),
        )

    def validate_purchase_order(self, order):
        receivable = {
            PurchaseOrder.Status.APPROVED,
            PurchaseOrder.Status.PARTIALLY_RECEIVED,
        }
        if order.status not in receivable:
            raise serializers.ValidationError(
                "Goods can only be received against an approved purchase order."
            )
        return order

    def validate_lines(self, lines):
        if self.instance is not None and not self.instance.is_editable():
            raise serializers.ValidationError(
                "Line items can only be changed while the GRN is a draft."
            )
        return lines

    def _build_line(self, order, line):
        po_line = line["purchase_order_line"]
        if po_line.purchase_order_id != order.pk:
            raise serializers.ValidationError(
                {"lines": "A receipt line must belong to the purchase order being received."}
            )
        qty = line["quantity_received"]
        outstanding = po_line.quantity_outstanding
        if qty > outstanding:
            raise serializers.ValidationError(
                {
                    "lines": (
                        f"Cannot receive more than outstanding for "
                        f"{po_line.product.name}. Outstanding: {outstanding}."
                    )
                }
            )
        unit_cost = line.get("unit_cost")
        if unit_cost is None:
            unit_cost = po_line.unit_cost
        return {
            "purchase_order_line": po_line,
            "product": po_line.product,
            "ordered_quantity": po_line.quantity,
            "previously_received": po_line.quantity_received,
            "quantity_received": qty,
            "unit_cost": unit_cost,
            "batch_number": line.get("batch_number") or "",
            "expiry_date": line.get("expiry_date"),
        }

    def _default_lines(self, order):
        built = []
        for po_line in order.lines.select_related("product"):
            outstanding = po_line.quantity_outstanding
            if outstanding <= 0:
                continue
            built.append(
                {
                    "purchase_order_line": po_line,
                    "product": po_line.product,
                    "ordered_quantity": po_line.quantity,
                    "previously_received": po_line.quantity_received,
                    "quantity_received": outstanding,
                    "unit_cost": po_line.unit_cost,
                    "batch_number": "",
                    "expiry_date": None,
                }
            )
        if not built:
            raise serializers.ValidationError(
                {"lines": "Nothing remains to receive on this purchase order."}
            )
        return built

    def create(self, validated_data):
        lines = validated_data.pop("lines", None)
        order = validated_data["purchase_order"]
        validated_data["branch"] = order.branch
        validated_data["supplier"] = order.supplier
        if not validated_data.get("received_date"):
            from django.utils import timezone

            validated_data["received_date"] = timezone.localdate()

        if lines:
            built = [self._build_line(order, line) for line in lines]
        else:
            built = self._default_lines(order)

        grn = GoodsReceivedNote.objects.create(**validated_data)
        GoodsReceivedLine.objects.bulk_create(
            GoodsReceivedLine(grn=grn, **data) for data in built
        )
        return grn

    def update(self, instance, validated_data):
        if not instance.is_editable():
            raise serializers.ValidationError(
                {"detail": "Only draft goods received notes can be edited."}
            )
        lines = validated_data.pop("lines", None)
        validated_data.pop("purchase_order", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data.keys(), "updated_at"] if validated_data else None)

        if lines is not None:
            instance.lines.all().delete()
            built = [self._build_line(instance.purchase_order, line) for line in lines]
            GoodsReceivedLine.objects.bulk_create(
                GoodsReceivedLine(grn=instance, **data) for data in built
            )
        return instance

