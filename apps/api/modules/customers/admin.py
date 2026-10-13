from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "organization", "points_balance", "deleted_at", "created_at")
    list_filter = ("organization", "deleted_at")
    search_fields = ("name", "phone")
    list_select_related = ("organization",)

    @admin.display(description="Points")
    def points_balance(self, obj):
        return obj.points_balance
