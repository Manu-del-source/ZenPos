from config.routing import ModuleRouter

from .views import AnalyticsViewSet

router = ModuleRouter()
router.register("analytics", AnalyticsViewSet, basename="analytics")

urlpatterns = router.urls
