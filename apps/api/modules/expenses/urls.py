from config.routing import ModuleRouter

from .views import ExpenseCategoryViewSet, ExpenseViewSet

router = ModuleRouter()
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-category")
router.register("expenses", ExpenseViewSet, basename="expense")

urlpatterns = router.urls
