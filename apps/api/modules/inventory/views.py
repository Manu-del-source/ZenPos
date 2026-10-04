from rest_framework import mixins, viewsets

from modules.core.mixins import OrganizationScopedMixin

from .models import StockAdjustment
from .serializers import StockAdjustmentSerializer


class StockAdjustmentViewSet(
    OrganizationScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Stock adjustments, scoped through the product's organization.

    There is deliberately no update and no delete. An adjustment is the record of
    *why* stock moved: editing its quantity would desynchronise it from the stock
    it already changed, and deleting it would leave that change unexplained. A
    mistake is corrected by recording a reversing adjustment, which keeps both
    facts in the history. Phase 5 replaces this with the full branch ledger.
    """

    queryset = StockAdjustment.objects.select_related("product", "user").all()
    serializer_class = StockAdjustmentSerializer
    organization_field = "product__organization"

    required_permissions = ("inventory.view",)
    required_permissions_by_action = {
        "create": ("inventory.adjust",),
    }
