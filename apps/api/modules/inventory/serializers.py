from django.db import transaction
from rest_framework import serializers

from modules.catalog.models import Product
from modules.core.audit import record_audit, snapshot
from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import StockAdjustment


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
        adjustments cannot interleave and lose an update. The audit row is
        written inside the same transaction: if the stock write fails, the
        record of the attempt fails with it.
        """
        product = Product.objects.select_for_update().get(
            pk=validated_data["product"].pk
        )
        before = snapshot(product, ("stock_level",))
        adjustment = StockAdjustment.objects.create(
            **{**validated_data, "product": product}
        )
        product.stock_level += adjustment.quantity
        product.save(update_fields=["stock_level", "updated_at"])
        record_audit(
            action="stock.adjusted",
            entity_type="product",
            entity_id=product.pk,
            actor=self.context["request"].user,
            request=self.context.get("request"),
            before=before,
            after={"stock_level": product.stock_level},
        )
        return adjustment
