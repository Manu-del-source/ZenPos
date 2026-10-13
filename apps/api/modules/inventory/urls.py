from config.routing import ModuleRouter

from .views import (
    InventoryMovementViewSet,
    StockAdjustmentViewSet,
    StockCountViewSet,
    StockTransferViewSet,
)

router = ModuleRouter()
router.register("adjustments", StockAdjustmentViewSet, basename="adjustment")
router.register("inventory-movements", InventoryMovementViewSet, basename="inventory-movement")
router.register("stock-counts", StockCountViewSet, basename="stock-count")
router.register("transfers", StockTransferViewSet, basename="stock-transfer")

urlpatterns = router.urls
