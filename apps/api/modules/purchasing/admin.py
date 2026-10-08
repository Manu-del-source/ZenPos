from django.contrib import admin

from .models import (
    GoodsReceivedLine,
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_name", "phone", "email", "status", "organization")
    list_filter = ("status", "organization")
    search_fields = ("name", "contact_name", "phone", "email")
    list_select_related = ("organization",)


class PurchaseOrderLineInline(admin.TabularInline):
    model = PurchaseOrderLine
    extra = 0
    autocomplete_fields = ("product",)


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "supplier",
        "branch",
        "status",
        "expected_date",
        "organization",
    )
    list_filter = ("status", "organization", "branch")
    search_fields = ("number", "supplier__name")
    list_select_related = ("supplier", "branch", "organization")
    inlines = (PurchaseOrderLineInline,)
    readonly_fields = ("number", "status", "created_by", "approved_by", "approved_at")


class GoodsReceivedLineInline(admin.TabularInline):
    model = GoodsReceivedLine
    extra = 0
    autocomplete_fields = ("product", "purchase_order_line")


@admin.register(GoodsReceivedNote)
class GoodsReceivedNoteAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "purchase_order",
        "supplier",
        "branch",
        "status",
        "received_date",
        "organization",
    )
    list_filter = ("status", "organization", "branch")
    search_fields = ("number", "delivery_note", "purchase_order__number")
    list_select_related = ("purchase_order", "supplier", "branch", "organization")
    inlines = (GoodsReceivedLineInline,)
    readonly_fields = (
        "number",
        "status",
        "received_by",
        "posted_by",
        "posted_at",
    )
