from config.routing import ModuleRouter

from .views import PurchaseOrderViewSet, SupplierViewSet

router = ModuleRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")

urlpatterns = router.urls
