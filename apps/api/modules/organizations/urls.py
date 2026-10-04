from config.routing import ModuleRouter

from .views import OrganizationViewSet

router = ModuleRouter()
router.register("organizations", OrganizationViewSet, basename="organization")

urlpatterns = router.urls
