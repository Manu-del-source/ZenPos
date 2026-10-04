from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.core.mixins import OrganizationScopedMixin

from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Customers of the caller's organization.

    ``customers.manage`` covers both reading and writing, because the permission
    vocabulary has no separate read code for customers and a cashier who cannot
    look a customer up cannot attach one to a sale. The tenant boundary is the
    queryset: another organization's customer is a 404, never a read.
    """

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    required_permissions = ("customers.manage",)

    @action(detail=False, methods=["get"])
    def search(self, request):
        """Look up a single customer by phone number, within the caller's organization."""
        phone = request.query_params.get("phone")
        if phone:
            customer = self.get_queryset().filter(phone=phone).first()
            if customer:
                return Response(CustomerSerializer(customer).data)

        return Response(
            {"detail": "Customer not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
