from config.routing import ModuleRouter

from .views import CustomerViewSet

router = ModuleRouter()
router.register("customers", CustomerViewSet, basename="customer")

urlpatterns = router.urls
