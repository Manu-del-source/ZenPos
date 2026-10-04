from config.routing import ModuleRouter

from .views import PaymentViewSet

router = ModuleRouter()
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = router.urls
