from config.routing import ModuleRouter

from .views import BranchViewSet

router = ModuleRouter()
router.register("branches", BranchViewSet, basename="branch")

urlpatterns = router.urls
