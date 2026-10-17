from config.routing import ModuleRouter

from .views import PaymentViewSet, match_till_transaction, unmatched_till_transactions

from django.urls import path

router = ModuleRouter()
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = router.urls + [
    path("mpesa/till-transactions/", unmatched_till_transactions, name="mpesa-till-transactions"),
    path("mpesa/till-transactions/match/", match_till_transaction, name="mpesa-till-match"),
]
