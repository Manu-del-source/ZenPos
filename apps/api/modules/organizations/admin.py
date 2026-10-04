from django.contrib import admin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "currency", "timezone", "is_active")
    list_filter = ("is_active", "currency")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
