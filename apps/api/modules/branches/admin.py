from django.contrib import admin

from .models import Branch


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "organization", "phone", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "code", "phone")
    list_select_related = ("organization",)
