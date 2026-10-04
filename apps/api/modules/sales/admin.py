from django.contrib import admin

from .models import Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "sale_number",
        "cashier",
        "customer",
        "total_amount",
        "payment_method",
        "created_at",
    )
    list_filter = ("payment_method", "created_at")
    search_fields = ("sale_number", "customer__name", "customer__phone")
    inlines = [SaleItemInline]
