from config.routing import ModuleRouter

from .views import GoodsReceivedNoteViewSet, PurchaseOrderViewSet, SupplierViewSet

router = ModuleRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("goods-receipts", GoodsReceivedNoteViewSet, basename="goods-receipt")

urlpatterns = router.urls
