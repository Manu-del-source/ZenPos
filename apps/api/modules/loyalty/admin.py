from django.contrib import admin

from .models import LoyaltyAccount, LoyaltyLedger, LoyaltyRule


@admin.register(LoyaltyRule)
class LoyaltyRuleAdmin(admin.ModelAdmin):
    list_display = ("organization", "points", "amount", "is_active")


@admin.register(LoyaltyAccount)
class LoyaltyAccountAdmin(admin.ModelAdmin):
    list_display = ("customer", "points_balance", "organization")
    search_fields = ("customer__name", "customer__phone")


@admin.register(LoyaltyLedger)
class LoyaltyLedgerAdmin(admin.ModelAdmin):
    list_display = ("created_at", "customer", "action", "points", "balance_after")
    list_filter = ("action",)
    readonly_fields = (
        "organization",
        "account",
        "customer",
        "branch",
        "points",
        "action",
        "reference_type",
        "reference_id",
        "actor",
        "notes",
        "balance_after",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
