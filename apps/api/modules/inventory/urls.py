from config.routing import ModuleRouter

from .views import StockAdjustmentViewSet

router = ModuleRouter()
router.register("adjustments", StockAdjustmentViewSet, basename="adjustment")

urlpatterns = router.urls
