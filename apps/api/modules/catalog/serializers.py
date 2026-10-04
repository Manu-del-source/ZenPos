from django.db import transaction
from rest_framework import serializers

from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import (
    Brand,
    Category,
    PriceHistory,
    Product,
    ProductBarcode,
    TaxRate,
    Unit,
)


class CategorySerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    # A parent category from another organization would cross the tenant
    # boundary while looking like an ordinary hierarchy.
    organization_bound_fields = ("parent",)

    class Meta:
        model = Category
        fields = ("id", "organization", "parent", "name", "is_active")
        read_only_fields = ("id", "organization")


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "organization", "name")
        read_only_fields = ("id", "organization")


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ("id", "organization", "name", "abbreviation", "allows_fraction")
        read_only_fields = ("id", "organization")


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = ("id", "organization", "name", "rate", "is_inclusive")
        read_only_fields = ("id", "organization")


class ProductBarcodeSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    organization_bound_fields = ("product",)

    class Meta:
        model = ProductBarcode
        fields = ("id", "organization", "product", "barcode", "is_primary", "created_at")
        read_only_fields = ("id", "organization", "created_at")


class PriceHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.ReadOnlyField(source="changed_by.username")

    class Meta:
        model = PriceHistory
        fields = (
            "id",
            "product",
            "old_price",
            "new_price",
            "changed_by",
            "changed_by_name",
            "reason",
            "created_at",
        )
        read_only_fields = fields


class ProductSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    organization_bound_fields = ("category", "brand", "unit", "tax_rate")

    barcodes = ProductBarcodeSerializer(many=True, read_only=True)
    category_name = serializers.ReadOnlyField(source="category.name")
    brand_name = serializers.ReadOnlyField(source="brand.name")
    unit_abbreviation = serializers.ReadOnlyField(source="unit.abbreviation")
    tax_rate_name = serializers.ReadOnlyField(source="tax_rate.name")

    class Meta:
        model = Product
        fields = (
            "id",
            "organization",
            "name",
            "sku",
            "category",
            "category_name",
            "brand",
            "brand_name",
            "unit",
            "unit_abbreviation",
            "tax_rate",
            "tax_rate_name",
            "price",
            "cost_price",
            "low_stock_threshold",
            "track_inventory",
            "is_active",
            "stock_level",
            "barcodes",
            "created_at",
            "updated_at",
        )
        # Stock is read-only here on purpose: it may only move through a recorded
        # adjustment or a sale, never by patching the product.
        read_only_fields = (
            "id",
            "organization",
            "stock_level",
            "created_at",
            "updated_at",
        )

    @transaction.atomic
    def update(self, instance, validated_data):
        """Apply the update and, if the selling price moved, record why."""
        old_price = instance.price
        product = super().update(instance, validated_data)

        if old_price != product.price:
            user = getattr(self.context.get("request"), "user", None)
            PriceHistory.objects.create(
                product=product,
                old_price=old_price,
                new_price=product.price,
                changed_by=user
                if getattr(user, "is_authenticated", False)
                else None,
            )

        return product
