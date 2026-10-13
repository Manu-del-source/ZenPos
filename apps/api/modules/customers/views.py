from django.db import transaction
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from modules.core.audit import record_audit, snapshot
from modules.core.mixins import OrganizationScopedMixin

from .models import Customer
from .serializers import CustomerSerializer


class CustomerViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    """Customers of the caller's organization.

    ``customers.manage`` covers both reading and writing, because the permission
    vocabulary has no separate read code for customers and a cashier who cannot
    look a customer up cannot attach one to a sale. The tenant boundary is the
    queryset: another organization's customer is a 404, never a read.

    ``DELETE`` archives rather than deletes: a customer who has bought things
    is part of the sales history, and deleting the row would break the
    explainability of who bought what. Archiving hides them from the directory
    (list, retrieve and search all answer 404 from then on) and frees their
    phone number for reuse, while every past sale keeps pointing at the row.
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

    def destroy(self, request, *args, **kwargs):
        """Archive the customer instead of deleting them (see class docstring)."""
        customer = self.get_object()

        with transaction.atomic():
            before = snapshot(customer)
            customer.soft_delete()
            record_audit(
                action="customer.archived",
                entity_type="customer",
                entity_id=customer.pk,
                actor=request.user,
                request=request,
                before=before,
                after={"deleted_at": str(customer.deleted_at)},
            )
        return Response(
            CustomerSerializer(customer, context={"request": request}).data,
            status=status.HTTP_200_OK,
        )
