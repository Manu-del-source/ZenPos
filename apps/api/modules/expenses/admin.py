from django.contrib import admin

from .models import Expense, ExpenseCategory


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_active", "created_at")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "organization__name")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    """Append-only money rows: admin may read and add, never edit or remove.

    The Django admin is held to the same rule as the API (ADR-0013, ADR-0015):
    a financial record is corrected by a reversal, not a silent rewrite.
    """

    can_delete = False
    list_display = (
        "expense_number",
        "date",
        "branch",
        "category",
        "amount",
        "reference",
        "is_reversal",
        "created_by",
    )
    list_filter = ("date", "branch", "category", "organization")
    search_fields = ("expense_number", "reference", "notes")
    readonly_fields = (
        "organization",
        "branch",
        "category",
        "expense_number",
        "date",
        "amount",
        "reference",
        "notes",
        "created_by",
        "reversal_of",
        "created_at",
        "updated_at",
    )

    def has_change_permission(self, request, obj=None):
        # ``can_delete = False`` handles removal; this shuts the change view
        # down too, leaving only add (new rows) and read.
        return False
