from django.contrib import admin

from .models import Supplier


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_name", "phone", "email", "status", "organization")
    list_filter = ("status", "organization")
    search_fields = ("name", "contact_name", "phone", "email")
    list_select_related = ("organization",)
