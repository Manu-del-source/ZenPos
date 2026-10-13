from django.contrib import admin

from .models import Branch, CashMovement, CashSession, Till


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "phone", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "code", "phone")
    list_select_related = ("organization",)


@admin.register(Till)
class TillAdmin(admin.ModelAdmin):
    list_display = ("name", "branch", "organization", "is_active")
    list_filter = ("is_active", "branch", "organization")
    search_fields = ("name", "branch__code")
    list_select_related = ("branch", "organization")


@admin.register(CashSession)
class CashSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "till",
        "branch",
        "opened_by",
        "status",
        "opening_cash",
        "counted_cash",
        "expected_cash",
        "cash_variance",
        "closed_at",
    )
    list_filter = ("status", "branch")
    search_fields = ("till__name", "opened_by__username")
    list_select_related = ("till", "branch", "opened_by", "closed_by")
    # The financial record is append-only over the API; admin is support
    # tooling, so fields are read-only rather than deleted.
    readonly_fields = [f.name for f in CashSession._meta.concrete_fields if f.name != "id"]
    date_hierarchy = "created_at"


@admin.register(CashMovement)
class CashMovementAdmin(admin.ModelAdmin):
    list_display = (
        "session",
        "movement_type",
        "source",
        "amount",
        "reason",
        "created_by",
        "created_at",
    )
    list_filter = ("movement_type", "source", "branch")
    search_fields = ("reason", "reference", "session__id")
    list_select_related = ("session", "created_by")
    readonly_fields = [f.name for f in CashMovement._meta.concrete_fields if f.name != "id"]
    date_hierarchy = "created_at"
