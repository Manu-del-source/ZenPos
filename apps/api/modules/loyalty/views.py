from django.db import transaction
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST as HTTP_BAD_REQUEST

from modules.core.mixins import OrganizationScopedMixin
from modules.customers.models import Customer

from .models import LoyaltyAccount, LoyaltyLedger, LoyaltyRule
from .serializers import (
    LoyaltyAccountSerializer,
    LoyaltyAdjustSerializer,
    LoyaltyLedgerSerializer,
    LoyaltyRuleSerializer,
)
from .services import apply_ledger, get_or_create_account, rule_for


class LoyaltyRuleViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = LoyaltyRule.objects.all()
    serializer_class = LoyaltyRuleSerializer
    required_permissions = ("loyalty.manage",)

    def perform_create(self, serializer):
        super().perform_create(serializer)


class LoyaltyAccountViewSet(
    OrganizationScopedMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = LoyaltyAccount.objects.select_related("customer").prefetch_related(
        "entries__actor", "entries__branch"
    )
    serializer_class = LoyaltyAccountSerializer
    required_permissions = ("customers.manage",)
    required_permissions_by_action = {
        "earn": ("loyalty.manage",),
        "redeem": ("loyalty.manage",),
        "adjust": ("loyalty.manage",),
        "ensure": ("customers.manage",),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        customer = self.request.query_params.get("customer")
        if customer:
            queryset = queryset.filter(customer_id=customer)
        return queryset

    @action(detail=False, methods=["post"])
    def ensure(self, request):
        """Open an account for a customer if they do not have one."""
        customer_id = request.data.get("customer")
        customer = Customer.objects.filter(
            pk=customer_id, organization=request.user.organization
        ).first()
        if customer is None:
            return Response({"detail": "Customer not found."}, status=HTTP_BAD_REQUEST)
        account = get_or_create_account(customer)
        return Response(self.get_serializer(account).data)

    def _mutate(self, request, default_action):
        serializer = LoyaltyAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        account = self.get_object() if self.action != "adjust" or getattr(self, "basename", "") else None
        # detail actions have an account; list-style adjust uses customer id.
        if "pk" in self.kwargs:
            account = self.get_object()
            customer = account.customer
        else:
            customer = Customer.objects.filter(
                pk=data.get("customer"), organization=request.user.organization
            ).first()
            if customer is None:
                return Response({"detail": "Customer not found."}, status=HTTP_BAD_REQUEST)
        action = default_action
        points = data["points"]
        if action == LoyaltyLedger.Action.REDEEM and points > 0:
            points = -points
        with transaction.atomic():
            entry = apply_ledger(
                customer=customer,
                points=points,
                action=action,
                organization=customer.organization,
                actor=request.user,
                notes=data.get("notes") or "",
                request=request,
            )
        account = get_or_create_account(customer)
        payload = LoyaltyAccountSerializer(account, context={"request": request}).data
        payload["entry"] = LoyaltyLedgerSerializer(entry).data if entry else None
        return Response(payload)

    @action(detail=True, methods=["post"])
    def earn(self, request, pk=None):
        return self._mutate(request, LoyaltyLedger.Action.EARN)

    @action(detail=True, methods=["post"])
    def redeem(self, request, pk=None):
        return self._mutate(request, LoyaltyLedger.Action.REDEEM)

    @action(detail=True, methods=["post"])
    def adjust(self, request, pk=None):
        return self._mutate(request, LoyaltyLedger.Action.ADJUST)
