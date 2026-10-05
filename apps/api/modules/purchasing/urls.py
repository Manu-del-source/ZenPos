from config.routing import ModuleRouter

from .views import SupplierViewSet

router = ModuleRouter()
router.register("suppliers", SupplierViewSet, basename="supplier")

urlpatterns = router.urls
