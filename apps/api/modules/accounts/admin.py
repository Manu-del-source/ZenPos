from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Permission, Role, RolePermission, User, UserBranchAccess, UserRole


class UserRoleInline(admin.TabularInline):
    model = UserRole
    extra = 0
    autocomplete_fields = ("role", "branch")


class UserBranchAccessInline(admin.TabularInline):
    model = UserBranchAccess
    extra = 0
    autocomplete_fields = ("branch",)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ("username", "email", "organization", "default_branch", "is_staff")
    list_filter = DjangoUserAdmin.list_filter + ("organization",)
    search_fields = ("username", "email", "first_name", "last_name")
    list_select_related = ("organization", "default_branch")
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "ZenPOS",
            {"fields": ("organization", "default_branch")},
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "ZenPOS",
            {"fields": ("organization", "default_branch")},
        ),
    )
    inlines = [UserRoleInline, UserBranchAccessInline]


class RolePermissionInline(admin.TabularInline):
    model = RolePermission
    extra = 0
    autocomplete_fields = ("permission",)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "organization", "is_system")
    list_filter = ("is_system", "organization")
    search_fields = ("name", "description")
    inlines = [RolePermissionInline]


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "module", "description")
    list_filter = ("module",)
    search_fields = ("code", "description")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "branch", "created_at")
    list_select_related = ("user", "role", "branch")
    autocomplete_fields = ("user", "role", "branch")


@admin.register(UserBranchAccess)
class UserBranchAccessAdmin(admin.ModelAdmin):
    list_display = ("user", "branch", "is_default")
    list_filter = ("is_default",)
    list_select_related = ("user", "branch")
    autocomplete_fields = ("user", "branch")
