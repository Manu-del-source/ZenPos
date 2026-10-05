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

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from modules.core.audit import record_audit
from modules.sales.services import restore_sale_stock

from .base import PaymentCallbackError, PaymentGatewayError, PaymentProvider
from .models import Payment, PaymentAttempt, WebhookEvent

#: A second STK push is refused while one is in flight, so a double-tap at the
#: till cannot bill the customer twice. Ported from the legacy Node service,
#: where ADR-0001 calls out that this check was worth keeping.
PENDING_STK_WINDOW = timezone.timedelta(minutes=5)

#: How long a PENDING STK request is left alone before polling asks Safaricom
#: for the truth. The customer's prompt is long expired by then, so a missing
#: callback is either late delivery or a lost message.
STK_RECONCILE_AFTER = timezone.timedelta(minutes=5)

#: The point at which an unverifiable payment stops holding stock. Reaching it
#: means the provider could not be asked (or would not answer), which is very
#: different from "the provider said no".
STK_HARD_TIMEOUT = timezone.timedelta(minutes=10)

#: Whole shillings are what STK push charges, so a callback amount may differ
#: from the sale total by the rounding. A whole shilling of slack covers that
#: and nothing else.
AMOUNT_TOLERANCE = Decimal("1.00")


def release_mpesa_stock_reservation(*, sale, actor=None, request=None) -> int:
    """Release stock reserved for an M-Pesa sale exactly once.

    A thin, well-named entry point onto the shared ledger restore, which is
    idempotent by construction: calling it twice restores nothing the second
    time.
    """
    return restore_sale_stock(
        sale=sale,
        actor=actor,
        request=request,
        reason="M-Pesa payment not completed",
        audit_action="stock.reservation_released",
    )


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


def _attempt_for(payment) -> PaymentAttempt | None:
    """The attempt that carries the provider's request id, newest first."""
    return (
        payment.attempts.exclude(checkout_request_id="")
        .order_by("-attempt_number")
        .first()
    )


def expected_provider_amount(payment) -> Decimal:
    """What we asked the provider to charge, in whole shillings.

    The attempt's ``provider_amount`` is what was actually sent (STK push
    charges whole shillings), which is the number a callback should echo. The
    payment total is the fallback for a payment with no attempt row.
    """
    attempt = _attempt_for(payment)
    if attempt is not None and attempt.provider_amount is not None:
        return attempt.provider_amount
    return payment.amount


def _record_webhook_event(*, provider_name: str, external_id: str, payload) -> bool:
    """Store the callback, answering ``False`` if it was already stored.

    Uniqueness is the database's job: the ``(provider, external_id)``
    constraint is what makes two concurrent redeliveries safe, and the nested
    atomic block is a savepoint so losing that race does not poison the
    surrounding transaction.
    """
    try:
        with transaction.atomic():
            WebhookEvent.objects.create(
                provider=provider_name,
                external_id=external_id,
                payload=payload,
            )
    except IntegrityError:
        return False
    return True


def handle_mpesa_callback(*, provider: PaymentProvider, payload, request=None) -> dict:
    """Process one M-Pesa callback: verify, de-duplicate, complete.

    Trust is layered (ADR-0012): the caller has already matched the secret URL
    segment; here the ``CheckoutRequestID`` must match an attempt we issued,
    the amount must match what we asked for, and the ``webhook_events`` unique
    constraint makes a redelivery a no-op that still answers 200 — Safaricom
    retries non-200 responses, which is correct for real failures but would
    duplicate work on mere redelivery.

    A callback for a payment that already settled (because polling reconciled
    it first, say) is answered 200 as a duplicate rather than rejected, so
    Safaricom does not retry a decision that was already made.

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
            settled = (
                Payment.objects.filter(
                    method=Payment.Method.MPESA,
                    attempts__checkout_request_id=callback.checkout_request_id,
                )
                .exclude(status=Payment.Status.PENDING)
                .first()
            )
            if settled is not None:
                # We already know the outcome (a poll reconciled it, or an
                # earlier copy of this callback arrived). Answer 200: there is
                # nothing left to decide.
                _record_webhook_event(
                    provider_name=provider.provider_name,
                    external_id=callback.external_id,
                    payload=payload,
                )
                return {"processed": False, "duplicate": True, "status": settled.status}

            # Not a payment we asked for. Rejected, and never stored as a
            # webhook event: this table must not carry success semantics for
            # requests we did not issue (ADR-0012).
            raise PaymentCallbackError(
                "No pending payment matches this callback's CheckoutRequestID."
            )

        if not _record_webhook_event(
            provider_name=provider.provider_name,
            external_id=callback.external_id,
            payload=payload,
        ):
            # IntegrityError from the unique (provider, external_id)
            # constraint: a redelivery. Answer 200 without re-effecting
            # anything.
            return {"processed": False, "duplicate": True, "status": payment.status}

        mismatch = callback.success and not _amount_matches(payment, callback.amount)

        if callback.success and not mismatch:
            payment.status = Payment.Status.COMPLETED
            payment.provider_reference = callback.provider_reference
            payment.save(update_fields=["status", "provider_reference", "updated_at"])
            audit_action = "payment.completed"
        else:
            # A success we cannot account for fails closed, so a mis-reported
            # amount never enters the paid ledger; the audit row keeps the
            # evidence for whoever reconciles the till. A provider-reported
            # failure releases the reservation it was holding.
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            release_mpesa_stock_reservation(sale=payment.sale, request=request)
            audit_action = "payment.amount_mismatch" if mismatch else "payment.failed"

        _mark_processed(provider.provider_name, callback.external_id)

        record_audit(
            action=audit_action,
            entity_type="payment",
            entity_id=payment.pk,
            request=request,
            before={"status": Payment.Status.PENDING},
            after={
                "status": payment.status,
                "provider_reference": payment.provider_reference or callback.provider_reference,
                "result": callback.result_desc,
                # Present only on a mismatch, where it is the whole point.
                **(
                    {
                        "expected_amount": str(expected_provider_amount(payment)),
                        "reported_amount": (
                            None if callback.amount is None else str(callback.amount)
                        ),
                    }
                    if mismatch
                    else {}
                ),
            },
        )

    return {"processed": True, "duplicate": False, "status": payment.status}


def _amount_matches(payment, reported: Decimal | None) -> bool:
    """Whether the provider's reported amount is the one we asked for.

    A callback that carries no amount (some sandbox responses omit it) is not
    treated as a mismatch: the request id and the secret URL have already
    established this is our payment, and refusing to complete on a missing
    optional field would strand a real payment.
    """
    if reported is None:
        return True
    expected = expected_provider_amount(payment)
    return abs(Decimal(reported) - Decimal(expected)) <= AMOUNT_TOLERANCE


def _mark_processed(provider_name: str, external_id: str) -> None:
    WebhookEvent.objects.filter(provider=provider_name, external_id=external_id).update(
        processed_at=timezone.now()
    )


def reconcile_pending_payment(*, payment, provider, request=None) -> Payment:
    """Ask the provider what really happened to a pending STK request.

    A lost callback is the dangerous case, not the abandoned one: the money may
    already have moved while our row still says PENDING, and the retry that
    follows would charge the customer twice. Safaricom's own status query is
    the only authority that can settle it, so polling calls it before any
    retry is allowed.

    Returns the payment, refreshed. A provider that cannot be reached leaves
    the payment PENDING — unknowable is not the same as failed.
    """
    attempt = _attempt_for(payment)
    if attempt is None:
        return payment

    result = provider.query(attempt.checkout_request_id)
    result_code = result.get("ResultCode")
    if result_code is None:
        # 500.001.1001 and friends: the request is not settled yet.
        return payment

    try:
        code = int(result_code)
    except (TypeError, ValueError):
        return payment

    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("sale").get(pk=payment.pk)
        if payment.status != Payment.Status.PENDING:
            # Something else settled it while the provider was being asked.
            return payment

        if code == 0:
            payment.status = Payment.Status.COMPLETED
            payment.provider_reference = str(result.get("MpesaReceiptNumber") or "")
            payment.save(update_fields=["status", "provider_reference", "updated_at"])
            audit_action = "payment.completed"
        else:
            payment.status = Payment.Status.FAILED
            payment.save(update_fields=["status", "updated_at"])
            release_mpesa_stock_reservation(sale=payment.sale, request=request)
            audit_action = "payment.failed"

        record_audit(
            action=audit_action,
            entity_type="payment",
            entity_id=payment.pk,
            request=request,
            before={"status": Payment.Status.PENDING},
            after={
                "status": payment.status,
                "source": "provider_query",
                "provider_reference": payment.provider_reference,
                "result": str(result.get("ResultDesc", ""))[:255],
            },
        )
    return payment

