from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from modules.core.audit import record_audit
from modules.core.mixins import BranchScopedMixin
from modules.sales.services import reserve_sale_stock

from .base import PaymentCallbackError, PaymentGatewayError
from .models import Payment
from .serializers import InitiatePaymentSerializer, PaymentSerializer
from .services import (
    STK_HARD_TIMEOUT,
    STK_RECONCILE_AFTER,
    assert_no_pending_stk,
    get_payment_provider,
    handle_mpesa_callback,
    initiate_payment,
    reconcile_pending_payment,
    release_mpesa_stock_reservation,
)


class PaymentViewSet(
    BranchScopedMixin,
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Payments against sales, created and polled by the POS.

    Initiation is a cashier act, so it is gated by ``sales.create``; polling is
    ``sales.view``. Scoping follows the sale: a payment inherits its tenant and
    its branch, so a supervisor cannot read another shop's takings through this
    table when the sales endpoint would refuse them.
    """

    queryset = (
        Payment.objects.select_related("sale", "received_by").prefetch_related("attempts").all()
    )
    serializer_class = PaymentSerializer
    organization_field = "sale__organization"
    branch_field = "sale__branch"

    required_permissions = ("sales.view",)
    required_permissions_by_action = {
        "create": ("sales.create",),
    }

    def get_serializer_class(self):
        if self.action == "create":
            return InitiatePaymentSerializer
        return PaymentSerializer

    def get_queryset(self):
        """Optional narrowing by sale, status or method.

        The POS recovers from a dropped connection with ``?sale=<id>``: after a
        push whose response never arrived, it asks what payments this sale
        already has instead of starting a second one. Filtering is additive —
        a request that sends no parameters gets the whole (scoped) list it
        always did.
        """
        queryset = super().get_queryset()
        params = self.request.query_params

        sale = params.get("sale")
        if sale:
            queryset = queryset.filter(sale_id=sale)

        status_param = params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.upper())

        method = params.get("method")
        if method:
            queryset = queryset.filter(method=method.upper())

        return queryset

    def retrieve(self, request, *args, **kwargs):
        payment = self.get_object()
        # A pending STK request must not be taken at face value. Once the
        # customer's prompt has expired, ask Safaricom what happened before the
        # POS is allowed to retry: a lost callback would otherwise mean a
        # second charge for the same sale.
        if (
            payment.method == Payment.Method.MPESA
            and payment.status == Payment.Status.PENDING
            and payment.created_at <= timezone.now() - STK_RECONCILE_AFTER
        ):
            payment = self._reconcile(payment)
        return Response(PaymentSerializer(payment, context={"request": request}).data)

    def _reconcile(self, payment):
        """Ask the provider, then fall back to a bounded timeout.

        The provider is the authority. Only when it cannot be asked at all —
        credentials absent, network down — does the hard timeout apply, and
        that path releases the reservation so an abandoned sale cannot hold
        stock forever. Neither path can mark a payment COMPLETED; that remains
        the callback's job, so a forged response here buys nothing.
        """
        try:
            provider = get_payment_provider()
        except ValueError:
            provider = None

        if provider is not None:
            try:
                return reconcile_pending_payment(payment=payment, provider=provider, request=None)
            except Exception:
                # A status poll must never 500 because a provider misbehaved;
                # the timeout below is the safety net.
                pass

        if payment.created_at <= timezone.now() - STK_HARD_TIMEOUT:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            release_mpesa_stock_reservation(sale=payment.sale, request=self.request)
            record_audit(
                action="payment.timed_out",
                entity_type="payment",
                entity_id=payment.pk,
                actor=self.request.user,
                request=self.request,
                before={"status": Payment.Status.PENDING},
                after={"status": payment.status},
            )
            payment.refresh_from_db()

        return payment


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
                sale = serializer.validated_data["sale"]
                assert_no_pending_stk(sale)
                # A retry after a failed attempt must hold the stock again
                # before the customer is asked for money a second time.
                reserve_sale_stock(sale=sale, actor=self.request.user, request=self.request)
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
