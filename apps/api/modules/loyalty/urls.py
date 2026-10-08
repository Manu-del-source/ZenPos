from config.routing import ModuleRouter

from .views import LoyaltyAccountViewSet, LoyaltyRuleViewSet

router = ModuleRouter()
router.register("loyalty-rules", LoyaltyRuleViewSet, basename="loyalty-rule")
router.register("loyalty-accounts", LoyaltyAccountViewSet, basename="loyalty-account")

urlpatterns = router.urls
