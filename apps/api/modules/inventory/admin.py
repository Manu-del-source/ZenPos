from django.contrib import admin

from .models import BranchStock, InventoryMovement, StockAdjustment, StockTransfer, StockTransferLine


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("product", "type", "quantity", "user", "created_at")
    list_filter = ("type",)
    search_fields = ("product__name", "product__barcodes__barcode", "notes")
    list_select_related = ("product", "user")


@admin.register(InventoryMovement)
class InventoryMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "product",
        "movement_type",
        "quantity",
        "quantity_before",
        "quantity_after",
        "branch",
        "actor",
    )
    list_filter = ("movement_type",)
    search_fields = ("product__name", "reference_id", "notes")
    list_select_related = ("product", "branch", "actor")
    readonly_fields = (
        "organization",
        "branch",
        "product",
        "quantity",
        "movement_type",
        "reference_type",
        "reference_id",
        "actor",
        "quantity_before",
        "quantity_after",
        "unit_cost",
        "notes",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BranchStock)
class BranchStockAdmin(admin.ModelAdmin):
    list_display = ("branch", "product", "quantity", "organization")
    list_filter = ("branch",)
    search_fields = ("product__name", "branch__name")
    list_select_related = ("branch", "product", "organization")


class StockTransferLineInline(admin.TabularInline):
    model = StockTransferLine
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(StockTransfer)
class StockTransferAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "source_branch",
        "destination_branch",
        "status",
        "organization",
    )
    list_filter = ("status", "organization")
    search_fields = ("number",)
    list_select_related = ("source_branch", "destination_branch", "organization")
    inlines = (StockTransferLineInline,)
    readonly_fields = (
        "number",
        "status",
        "requested_by",
        "requested_at",
        "approved_by",
        "approved_at",
        "dispatched_by",
        "dispatched_at",
        "received_by",
        "received_at",
    )
