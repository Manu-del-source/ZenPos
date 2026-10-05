from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from modules.core.audit import record_audit

from .base import PaymentCallbackError, PaymentGatewayError
from .models import Payment
from .serializers import InitiatePaymentSerializer, PaymentSerializer
from .services import (
    assert_no_pending_stk,
    get_payment_provider,
    handle_mpesa_callback,
    initiate_payment,
    release_mpesa_stock_reservation,
)


class PaymentViewSet(
    OrganizationScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Payments against sales, created and polled by the POS.

    Initiation is a cashier act, so it is gated by ``sales.create``; polling is
    ``sales.view``. Scoping follows the sale — ``Payment`` has no organization
    of its own, and phase 6 rebuilds ``Sale`` with a direct tenant column,
    which this filter path will then become.
    """

    queryset = (
        Payment.objects.select_related("sale", "received_by").prefetch_related("attempts").all()
    )
    serializer_class = PaymentSerializer
    organization_field = "sale__cashier__organization"

    required_permissions = ("sales.view",)
    required_permissions_by_action = {
        "create": ("sales.create",),
    }

    def get_serializer_class(self):
        if self.action == "create":
            return InitiatePaymentSerializer
        return PaymentSerializer

    def retrieve(self, request, *args, **kwargs):
        payment = self.get_object()
        # A stale STK request must not hold inventory forever when a provider
        # callback is lost. Polling the payment naturally performs the cleanup.
        if (
            payment.method == Payment.Method.MPESA
            and payment.status == Payment.Status.PENDING
            and payment.created_at <= timezone.now() - timezone.timedelta(minutes=10)
        ):
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            release_mpesa_stock_reservation(sale=payment.sale, request=request)
            payment.refresh_from_db()
        return Response(PaymentSerializer(payment, context={"request": request}).data)


    def create(self, request, *args, **kwargs):
        """Return the created payment using the public payment representation.

        The write serializer intentionally accepts only sale/method/phone. The
        POS needs the persisted payment id immediately so it can poll status,
        therefore the response is serialized with the read-only PaymentSerializer.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        payment = serializer.instance
        response_serializer = PaymentSerializer(payment, context={"request": request})
        headers = self.get_success_headers(response_serializer.data)
        return Response(response_serializer.data, status=201, headers=headers)

    def perform_create(self, serializer):
        """Create the payment, then start the provider exchange.

        The two steps are deliberately *not* one transaction. The provider
        exchange must be recorded — including its failure — even if this
        request dies partway, because after a successful STK push the customer
        really is looking at a prompt; erasing the attempt row would orphan
        that prompt. See ``initiate_payment``.
        """
        method = serializer.validated_data["method"]

        if method == Payment.Method.MPESA:
            try:
                # One un-answered push at a time, within the retry window.
                assert_no_pending_stk(serializer.validated_data["sale"])
                payment = serializer.save()
                initiate_payment(
                    payment=payment,
                    phone=serializer.validated_data["phone"],
                    provider=get_payment_provider(),
                )
            except (PaymentGatewayError, ValueError) as exc:
                # Provider configuration failures must also release the stock
                # reservation; otherwise a failed STK request could leave a
                # sale permanently consuming inventory.
                release_mpesa_stock_reservation(sale=serializer.validated_data["sale"])
                raise ValidationError({"detail": str(exc)}) from exc
            action = "payment.initiated"
        else:
            # Cash handed over at the till is completed money.
            payment = serializer.save(
                status=Payment.Status.COMPLETED,
                received_by=self.request.user,
            )
            action = "payment.completed"

        record_audit(
            action=action,
            entity_type="payment",
            entity_id=payment.pk,
            actor=self.request.user,
            request=self.request,
            after={
                "sale": str(payment.sale_id),
                "method": payment.method,
                "amount": str(payment.amount),
                "status": payment.status,
            },
        )


class CallbackRateThrottle(AnonRateThrottle):
    """Bound how many unauthenticated callback bodies are parsed per minute."""

    scope = "mpesa_callback"


@api_view(["POST"])
@permission_classes([])
@throttle_classes([CallbackRateThrottle])
def mpesa_callback(request, secret: str):
    """Safaricom's callback endpoint — anonymous, verified by construction.

    The trust layers, in order: the secret path segment (checked here, before
    anything else happens), the ``CheckoutRequestID`` match against a PENDING
    attempt we issued, and ``webhook_events`` idempotency. A wrong secret is a
    ``404`` — indistinguishable from any other unknown path, so this endpoint
    is not even confirmable to exist. Only a genuine callback with a matching
    secret transitions a payment; a rejected payload is never stored.
    """
    from django.conf import settings

    if not settings.MPESA_CALLBACK_SECRET or secret != settings.MPESA_CALLBACK_SECRET:
        raise NotFound("Unknown callback address.")

    try:
        result = handle_mpesa_callback(
            provider=get_payment_provider(), payload=request.data, request=request
        )
    except PaymentCallbackError as exc:
        # Unknown or unmatched callbacks are rejected with 400: Safaricom
        # should retry them, because a transient delivery failure looks
        # identical to a forged one from here.
        raise ValidationError({"detail": "Callback rejected."}) from exc

    return Response(result, status=200)
