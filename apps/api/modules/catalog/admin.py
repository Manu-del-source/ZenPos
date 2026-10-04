from django.contrib import admin

from .models import Brand, Category, PriceHistory, Product, ProductBarcode, TaxRate, Unit


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "parent", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("name",)


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("name", "organization")
    list_filter = ("organization",)
    search_fields = ("name",)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ("name", "abbreviation", "allows_fraction", "organization")
    list_filter = ("allows_fraction", "organization")
    search_fields = ("name", "abbreviation")


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = ("name", "rate", "is_inclusive", "organization")
    list_filter = ("is_inclusive", "organization")
    # Required: ProductAdmin references this admin in autocomplete_fields.
    search_fields = ("name",)


class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 0


class PriceHistoryInline(admin.TabularInline):
    model = PriceHistory
    extra = 0
    readonly_fields = ("old_price", "new_price", "changed_by", "reason", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category", "brand", "price", "cost_price", "is_active")
    list_filter = ("is_active", "track_inventory", "organization", "category", "brand")
    search_fields = ("name", "sku", "barcodes__barcode")
    list_select_related = ("organization", "category", "brand", "unit", "tax_rate")
    autocomplete_fields = ("category", "brand", "unit", "tax_rate")
    inlines = [ProductBarcodeInline, PriceHistoryInline]


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    list_display = ("barcode", "product", "organization", "is_primary")
    list_filter = ("is_primary", "organization")
    search_fields = ("barcode", "product__name")
    list_select_related = ("product", "organization")


@admin.register(PriceHistory)
class PriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("product", "old_price", "new_price", "changed_by", "created_at")
    list_select_related = ("product", "changed_by")
    search_fields = ("product__name",)
