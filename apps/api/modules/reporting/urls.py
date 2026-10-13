from config.routing import ModuleRouter

from .views import AnalyticsViewSet, FinanceViewSet

router = ModuleRouter()
router.register("analytics", AnalyticsViewSet, basename="analytics")
router.register("finance", FinanceViewSet, basename="finance")

urlpatterns = router.urls
