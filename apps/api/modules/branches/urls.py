from config.routing import ModuleRouter

from .views import BranchViewSet, CashSessionViewSet, TillViewSet

router = ModuleRouter()
router.register("branches", BranchViewSet, basename="branch")
router.register("tills", TillViewSet, basename="till")
router.register("cash-sessions", CashSessionViewSet, basename="cashsession")

urlpatterns = router.urls
