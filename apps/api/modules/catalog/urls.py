from config.routing import ModuleRouter

from .views import (
    BrandViewSet,
    CategoryViewSet,
    PriceHistoryViewSet,
    ProductBarcodeViewSet,
    ProductViewSet,
    TaxRateViewSet,
    UnitViewSet,
)

router = ModuleRouter()
router.register("products", ProductViewSet, basename="product")
router.register("product-barcodes", ProductBarcodeViewSet, basename="product-barcode")
router.register("categories", CategoryViewSet, basename="category")
router.register("brands", BrandViewSet, basename="brand")
router.register("units", UnitViewSet, basename="unit")
router.register("tax-rates", TaxRateViewSet, basename="tax-rate")
router.register("price-history", PriceHistoryViewSet, basename="price-history")

urlpatterns = router.urls
