from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "organization", "loyalty_points", "created_at")
    list_filter = ("organization",)
    search_fields = ("name", "phone")
    list_select_related = ("organization",)
