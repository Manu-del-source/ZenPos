from django.contrib import admin

from .models import IncomingTillTransaction, MerchantTillAccount


@admin.register(MerchantTillAccount)
class MerchantTillAccountAdmin(admin.ModelAdmin):
    list_display = ("shortcode", "environment", "organization", "branch", "is_active")
    list_filter = ("environment", "is_active", "organization")
    search_fields = ("shortcode", "organization__name", "branch__name")
    list_select_related = ("organization", "branch")


@admin.register(IncomingTillTransaction)
class IncomingTillTransactionAdmin(admin.ModelAdmin):
    """Operational ledger view; raw callback payload is intentionally omitted."""
    list_display = (
        "receipt_number", "amount", "currency", "transaction_time",
        "account", "status", "matched_sale", "matched_by",
    )
    list_filter = ("status", "currency", "account__environment")
    search_fields = ("receipt_number", "bill_reference", "third_party_transaction_id")
    list_select_related = ("account", "account__organization", "account__branch", "matched_sale", "matched_by")
    readonly_fields = (
        "account", "receipt_number", "amount", "currency", "transaction_time",
        "payer_phone", "payer_first_name", "payer_middle_name", "payer_last_name",
        "bill_reference", "third_party_transaction_id", "status", "matched_sale",
        "matched_payment", "matched_by", "matched_at", "created_at", "updated_at",
    )
    fields = readonly_fields
    ordering = ("-transaction_time",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
