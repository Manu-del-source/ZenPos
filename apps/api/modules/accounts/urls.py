from django.urls import path

from config.routing import ModuleRouter

from .views import (
    AuditLogViewSet,
    EmployeeViewSet,
    LoginView,
    LogoutView,
    MeView,
    PermissionViewSet,
    RefreshView,
    RoleViewSet,
    UserViewSet,
)

router = ModuleRouter()
router.register("roles", RoleViewSet, basename="role")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("users", UserViewSet, basename="user")
router.register("employees", EmployeeViewSet, basename="employee")
router.register("audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("auth/login/", LoginView.as_view(), name="token_obtain_pair"),
    path("auth/refresh/", RefreshView.as_view(), name="token_refresh"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    *router.urls,
]
