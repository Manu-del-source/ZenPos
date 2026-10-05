"""The service layer for payments: initiation, cash capture and callbacks.

Every state change here is atomic with the records that explain it: a payment
row without its attempt row — or a completion without its webhook event — is
money that cannot be reconciled. The sales domain calls
``complete_cash_payment``; only ``views.py`` calls ``initiate_payment`` and
``handle_mpesa_callback``, the latter being the one path allowed to mark a
payment COMPLETED.

Two rules from ADR-0012 shape this file:

- only a verified callback transitions a payment to COMPLETED — never a client
  message and never the caller of ``initiate_payment``;
- a redelivered callback is answered 200 without re-effecting anything, which
  is what the ``webhook_events`` unique constraint provides.
"""

from django.db import transaction
from django.utils import timezone

from modules.core.audit import record_audit
from modules.inventory.models import StockAdjustment

from .base import PaymentCallbackError, PaymentGatewayError, PaymentProvider
from .models import Payment, PaymentAttempt, WebhookEvent

#: A second STK push is refused while one is in flight, so a double-tap at the
#: till cannot bill the customer twice. Ported from the legacy Node service,
#: where ADR-0001 calls out that this check was worth keeping.
PENDING_STK_WINDOW = timezone.timedelta(minutes=5)


def release_mpesa_stock_reservation(*, sale, actor=None, request=None) -> int:
    """Release stock reserved for an M-Pesa sale exactly once."""
    release_note = f"Release M-Pesa reservation for sale {sale.sale_number}"
    if StockAdjustment.objects.filter(notes=release_note).exists():
        return 0
    released = 0
    adjustments = StockAdjustment.objects.filter(
        notes__startswith=f"Sale {sale.sale_number}", quantity__lt=0
    ).select_related("product")
    for adjustment in adjustments:
        product = adjustment.product
        product.stock_level += -adjustment.quantity
        product.save(update_fields=["stock_level", "updated_at"])
        StockAdjustment.objects.create(
            product=product, user=actor, quantity=-adjustment.quantity,
            type=StockAdjustment.AdjustmentType.RETURN, notes=release_note,
        )
        released += -adjustment.quantity
    if released:
        record_audit(
            action="stock.reservation_released", entity_type="sale", entity_id=sale.pk,
            actor=actor, request=request,
            after={"sale": sale.sale_number, "quantity": released},
        )
    return released


def get_payment_provider():
    """Build the M-Pesa adapter from the environment (ADR-0005).

    One construction site, so a credentials change is a configuration change
    and not a code hunt. A missing credential raises here, at the boundary of
    the payments domain, rather than mid-exchange.
    """
    from django.conf import settings

    from .mpesa import MpesaProvider

    return MpesaProvider(
        consumer_key=settings.MPESA_CONSUMER_KEY,
        consumer_secret=settings.MPESA_CONSUMER_SECRET,
        shortcode=settings.MPESA_SHORTCODE,
        passkey=settings.MPESA_PASSKEY,
        callback_url=settings.MPESA_CALLBACK_URL,
        environment=settings.MPESA_ENV,
        callback_secret=settings.MPESA_CALLBACK_SECRET,
    )


def complete_cash_payment(*, sale, amount, received_by) -> Payment:
    """Write a completed cash payment inside the caller's transaction.

    Called from the sale-creation flow, so there is nothing to initiate: cash
    handed over at the till is completed money. The caller owns the atomic
    block; this function deliberately does not open one, so the payment rolls
    back with the sale if anything in that block fails.
    """
    return Payment.objects.create(
        sale=sale,
        method=Payment.Method.CASH,
        amount=amount,
        status=Payment.Status.COMPLETED,
        received_by=received_by,
    )


def assert_no_pending_stk(sale) -> None:
    """Refuse a second STK push while one is young and unanswered.

    The window bounds the harm of a stale PENDING row: a customer who never
    entered their PIN is free to be asked again after it expires.
    """
    stale = timezone.now() - PENDING_STK_WINDOW
    if Payment.objects.filter(
        sale=sale,
        method=Payment.Method.MPESA,
        status=Payment.Status.PENDING,
        created_at__gte=stale,
    ).exists():
        raise PaymentGatewayError(
            "A payment request for this sale is already pending on the customer's phone."
        )


def initiate_payment(*, payment, phone: str, provider: PaymentProvider) -> Payment:
    """Start a provider payment and persist failures before returning the error."""
    attempt_number = PaymentAttempt.objects.filter(payment=payment).count() + 1
    provider_error = None

    with transaction.atomic():
        attempt = PaymentAttempt.objects.create(
            payment=payment,
            attempt_number=attempt_number,
            provider=provider.provider_name,
            checkout_request_id="",
            request_payload={},
            response_payload={},
            provider_amount=payment.amount,
            status=Payment.Status.PENDING,
        )

        try:
            initiation = provider.initiate(payment=payment, phone=phone)
        except PaymentGatewayError as exc:
            attempt.status = Payment.Status.FAILED
            attempt.error = str(exc)[:255]
            attempt.request_payload = exc.request_payload or {}
            attempt.response_payload = exc.response_payload or {}
            attempt.save(update_fields=["status", "error", "request_payload", "response_payload"])
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            record_audit(
                action="payment.failed",
                entity_type="payment",
                entity_id=payment.pk,
                after={
                    "sale": str(payment.sale_id),
                    "method": payment.method,
                    "error": str(exc)[:255],
                },
            )
            release_mpesa_stock_reservation(sale=payment.sale)
            provider_error = exc
        else:
            attempt.checkout_request_id = initiation.checkout_request_id
            attempt.request_payload = initiation.request_payload
            attempt.response_payload = initiation.response_payload
            attempt.provider_amount = initiation.provider_amount
            attempt.save(
                update_fields=[
                    "checkout_request_id",
                    "request_payload",
                    "response_payload",
                    "provider_amount",
                ]
            )
            record_audit(
                action="payment.initiated",
                entity_type="payment",
                entity_id=payment.pk,
                after={
                    "sale": str(payment.sale_id),
                    "method": payment.method,
                    "provider": provider.provider_name,
                    "checkout_request_id": initiation.checkout_request_id,
                },
            )

    if provider_error is not None:
        raise provider_error

    return payment


def handle_mpesa_callback(*, provider: PaymentProvider, payload, request=None) -> dict:
    """Process one M-Pesa callback: verify, de-duplicate, complete.

    Trust is layered (ADR-0012): the caller has already matched the secret URL
    segment; here the ``CheckoutRequestID`` must match a PENDING attempt we
    issued, and the ``webhook_events`` unique constraint makes a redelivery a
    no-op that still answers 200 — Safaricom retries non-200 responses, which
    is correct for real failures but would duplicate work on mere redelivery.

    Returns a small result dict for the view: ``{"processed": bool,
    "duplicate": bool, "status": str}``.
    """
    callback = provider.handle_callback(payload)

    if not callback.checkout_request_id:
        raise PaymentCallbackError("Callback carries no CheckoutRequestID.")

    # De-duplication first: a redelivery of an *already-processed* callback has
    # no PENDING payment left to match (it is COMPLETED or FAILED by now), and
    # rejecting it would make Safaricom retry forever. The external id already
    # in ``webhook_events`` proves this exact callback was handled, so it is
    # answered 200 without re-effecting anything. Uniqueness is enforced by the
    # database constraint; the SELECT here is only the fast path.
    if WebhookEvent.objects.filter(
        provider=provider.provider_name, external_id=callback.external_id
    ).exists():
        return {"processed": False, "duplicate": True, "status": ""}

    with transaction.atomic():
        # The only transition to COMPLETED in the system happens below, and
        # only for a PENDING payment whose attempt we issued. ``select_for_update``
        # serialises a callback against a genuine redelivery arriving
        # concurrently.
        payment = (
            Payment.objects.select_for_update()
            .filter(
                method=Payment.Method.MPESA,
                status=Payment.Status.PENDING,
                attempts__checkout_request_id=callback.checkout_request_id,
            )
            .select_related("sale")
            .first()
        )
        if payment is None:
            # Not a payment we asked for. Rejected, and never stored as a
            # webhook event: this table must not carry success semantics for
            # requests we did not issue (ADR-0012).
            raise PaymentCallbackError(
                "No pending payment matches this callback's CheckoutRequestID."
            )

        try:
            with transaction.atomic():
                WebhookEvent.objects.create(
                    provider=provider.provider_name,
                    external_id=callback.external_id,
                    payload=payload,
                )
        except Exception:
            # IntegrityError from the unique (provider, external_id)
            # constraint: a redelivery. Answer 200 without re-effecting
            # anything.
            return {"processed": False, "duplicate": True, "status": payment.status}

        if callback.success:
            payment.status = Payment.Status.COMPLETED
            payment.provider_reference = callback.provider_reference
            payment.save(update_fields=["status", "provider_reference", "updated_at"])
        else:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            release_mpesa_stock_reservation(
                sale=payment.sale,
                request=request,
            )

        WebhookEvent.objects.filter(
            provider=provider.provider_name, external_id=callback.external_id
        ).update(processed_at=timezone.now())

        record_audit(
            action="payment.completed" if callback.success else "payment.failed",
            entity_type="payment",
            entity_id=payment.pk,
            before={"status": Payment.Status.PENDING},
            after={
                "status": payment.status,
                "provider_reference": payment.provider_reference,
                "result": callback.result_desc,
            },
        )

    return {"processed": True, "duplicate": False, "status": payment.status}
