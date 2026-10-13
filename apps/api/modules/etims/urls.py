from config.routing import ModuleRouter

from .views import EtimsInvoiceViewSet

router = ModuleRouter()
router.register("etims/invoices", EtimsInvoiceViewSet, basename="etims-invoice")

urlpatterns = router.urls
