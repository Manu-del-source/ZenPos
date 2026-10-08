from config.routing import ModuleRouter

from .views import InventoryMovementViewSet, StockAdjustmentViewSet, StockTransferViewSet

router = ModuleRouter()
router.register("adjustments", StockAdjustmentViewSet, basename="adjustment")
router.register("inventory-movements", InventoryMovementViewSet, basename="inventory-movement")
router.register("transfers", StockTransferViewSet, basename="stock-transfer")

urlpatterns = router.urls
