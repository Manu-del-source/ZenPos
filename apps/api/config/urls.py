from django.contrib import admin
from django.urls import include, path

from . import views

# Each module owns its own router and urlconf. They are mounted under a shared
# prefix rather than each declaring its own, so the API surface stays in one
# readable place. ModuleRouter disables the per-router API root view, which
# would otherwise be registered once per module under the same URL name.
api_v2_patterns = [
    path("", include("modules.accounts.urls")),
    path("", include("modules.branches.urls")),
    path("", include("modules.catalog.urls")),
    path("", include("modules.customers.urls")),
    path("", include("modules.inventory.urls")),
    path("", include("modules.purchasing.urls")),
    path("", include("modules.organizations.urls")),
    path("", include("modules.payments.urls")),
    path("", include("modules.loyalty.urls")),
    path("", include("modules.reporting.urls")),
    path("", include("modules.sales.urls")),
    path("", include("modules.platform_admin.urls")),
]

urlpatterns = [
    path("", views.landing_page, name="landing"),
    path("healthz/", views.health_check, name="healthz"),
    path("admin/", admin.site.urls),
    path("api/v2/", include(api_v2_patterns)),
    # Provider callbacks live outside /api/v2/: they are anonymous, verified
    # by a secret path segment rather than a permission, and Safaricom is
    # given the full URL. See modules/payments/views.py (ADR-0012).
    path("callbacks/", include("modules.payments.mpesa_urls")),
]
