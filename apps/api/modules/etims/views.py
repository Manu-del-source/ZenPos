from rest_framework import mixins, viewsets

from modules.core.mixins import BranchScopedMixin

from .models import EtimsInvoice
from .serializers import EtimsInvoiceSerializer


class EtimsInvoiceViewSet(
    BranchScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """The compliance documents behind the sales, read-only.

    Writing happens through the domain (issuance on sale, cancellation on
    void) and nowhere else: a client endpoint that could create or edit an
    invoice would let the till decide what the tax document says. Scoping
    follows the sale, exactly as the payments viewset does, so a caller
    cannot read another shop's invoices through this table when the sales
    endpoint would refuse them.
    """

    queryset = EtimsInvoice.objects.select_related("sale", "sale__branch", "device").all()
    serializer_class = EtimsInvoiceSerializer
    organization_field = "sale__organization"
    branch_field = "sale__branch"

    required_permissions = ("sales.view",)

    def get_queryset(self):
        """Optional narrowing by sale, like the payments viewset."""
        queryset = super().get_queryset()
        sale = self.request.query_params.get("sale")
        if sale:
            queryset = queryset.filter(sale_id=sale)
        return queryset
