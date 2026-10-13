from django.urls import path

from config.routing import ModuleRouter

from .views import OrganizationViewSet, PlatformOrganizationViewSet

router = ModuleRouter()
router.register("organizations", OrganizationViewSet, basename="organization")

urlpatterns = [
    *router.urls,
    # Platform-operator surface: opening and closing tenants. These live
    # outside the tenant-facing ``organizations`` routes on purpose — the
    # tenant viewset never learns how to create or suspend, and the platform
    # routes never learn how to render a tenant's profile.
    path(
        "platform/organizations/",
        PlatformOrganizationViewSet.as_view({"post": "create"}),
        name="platform-organization-create",
    ),
    path(
        "platform/organizations/<uuid:pk>/suspend/",
        PlatformOrganizationViewSet.as_view({"post": "suspend"}),
        name="platform-organization-suspend",
    ),
    path(
        "platform/organizations/<uuid:pk>/activate/",
        PlatformOrganizationViewSet.as_view({"post": "activate"}),
        name="platform-organization-activate",
    ),
]
