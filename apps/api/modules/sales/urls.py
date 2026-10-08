from config.routing import ModuleRouter

from .views import SaleReturnViewSet, SaleViewSet

router = ModuleRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("returns", SaleReturnViewSet, basename="sale-return")

urlpatterns = router.urls
