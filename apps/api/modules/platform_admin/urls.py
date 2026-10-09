from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register(
    "platform/organizations", views.PlatformOrganizationViewSet, basename="platform-org"
)
router.register("platform/branches", views.PlatformBranchViewSet, basename="platform-branch")
router.register("platform/users", views.PlatformUserViewSet, basename="platform-user")
router.register("platform/audit-logs", views.PlatformAuditLogViewSet, basename="platform-audit")

urlpatterns = [
    path("platform/overview/", views.PlatformOverviewView.as_view()),
    path("platform/health/", views.PlatformHealthView.as_view()),
    path("platform/owners/", views.OwnerInviteView.as_view()),
    path("platform/invites/accept/", views.AcceptInviteView.as_view()),
    *router.urls,
]
