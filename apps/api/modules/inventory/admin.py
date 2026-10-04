from django.contrib import admin

from .models import StockAdjustment


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("product", "type", "quantity", "user", "created_at")
    list_filter = ("type",)
    # Barcodes moved off the product and into their own table in phase 3, so the
    # search path follows the relation. `product__barcode` is no longer a field
    # and made `manage.py check` fail.
    search_fields = ("product__name", "product__barcodes__barcode", "notes")
    list_select_related = ("product", "user")
