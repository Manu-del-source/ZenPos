from config.routing import ModuleRouter

from .views import SaleViewSet

router = ModuleRouter()
router.register("sales", SaleViewSet, basename="sale")

urlpatterns = router.urls
