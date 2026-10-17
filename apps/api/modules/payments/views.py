from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from modules.core.audit import record_audit
from modules.core.mixins import BranchScopedMixin
from modules.accounts.permissions import user_has_permission
from modules.sales.models import Sale
from modules.sales.services import record_sale_cash_in, reserve_sale_stock

from .base import PaymentCallbackError, PaymentGatewayError
from .models import IncomingTillTransaction, MerchantTillAccount, Payment
from .serializers import InitiatePaymentSerializer, PaymentSerializer
from .services import (
    STK_RECONCILE_AFTER,
    assert_no_pending_stk,
    get_payment_provider,
    handle_mpesa_callback,
    initiate_payment,
    outstanding_for,
    release_mpesa_stock_reservation,
    settle_pending_mpesa,
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

        Delegates to ``settle_pending_mpesa``, shared with the
        ``reap_stale_mpesa`` command: the provider is the authority, and only
        when it cannot be asked at all does the hard timeout apply, releasing
        the reservation so an abandoned sale cannot hold stock forever.
        Neither path can mark a payment COMPLETED; that remains the callback's
        job, so a forged response here buys nothing.
        """
        return settle_pending_mpesa(
            payment=payment, actor=self.request.user, request=self.request
        )


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

    def _assert_leg_affordable(self, sale, validated_data):
        """The leg re-check under the sale lock, where the authority lives.

        ``serializer.save`` has not run yet, so the leg amount is recomputed
        exactly as ``InitiatePaymentSerializer.create`` computes it: an
        explicit cash figure if given, otherwise the outstanding balance. Two
        concurrent legs serialize on the sale row, and only the first one
        that fits is written; the loser gets a 400, not an overpayment.
        """
        outstanding = outstanding_for(sale)
        if outstanding <= 0:
            raise ValidationError({"sale": "This sale is already fully paid."})
        leg_amount = validated_data.get("amount") or outstanding
        if leg_amount > outstanding:
            raise ValidationError(
                {
                    "amount": (
                        f"That amount exceeds the outstanding balance of {outstanding}."
                    )
                }
            )

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
                with transaction.atomic():
                    locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
                    self._assert_leg_affordable(locked_sale, serializer.validated_data)
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
            # Cash handed over at the till is completed money — and completed
            # cash is drawer cash, from whichever endpoint recorded it.
            sale = serializer.validated_data["sale"]
            with transaction.atomic():
                locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
                self._assert_leg_affordable(locked_sale, serializer.validated_data)
                payment = serializer.save(
                    status=Payment.Status.COMPLETED,
                    received_by=self.request.user,
                )
                record_sale_cash_in(
                    sale=locked_sale,
                    amount=payment.amount,
                    actor=self.request.user,
                    request=self.request,
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


# C2B manual Till reconciliation ------------------------------------------------

def _c2b_response(code=0, description="Accepted"):
    # Daraja C2B expects this acknowledgement shape for validation/confirmation.
    return Response({"ResultCode": code, "ResultDesc": description}, status=200)


def _c2b_transaction_fields(payload):
    """Validate and normalize the C2B fields without trusting client metadata."""
    if not isinstance(payload, dict):
        raise ValueError("Callback must be a JSON object.")
    receipt = str(payload.get("TransID") or "").strip()
    shortcode = str(payload.get("BusinessShortCode") or "").strip()
    try:
        amount = Decimal(str(payload.get("TransAmount"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid transaction amount.") from None
    if not receipt or len(receipt) > 64 or not shortcode or amount <= 0:
        raise ValueError("Required C2B transaction fields are missing.")
    timestamp_text = str(payload.get("TransTime") or "").strip()
    try:
        transaction_time = datetime.strptime(timestamp_text, "%Y%m%d%H%M%S")
    except ValueError:
        raise ValueError("Invalid transaction timestamp.") from None
    if timezone.is_naive(transaction_time):
        transaction_time = timezone.make_aware(transaction_time, timezone.get_current_timezone())
    return {
        "receipt_number": receipt,
        "shortcode": shortcode,
        "amount": amount,
        "transaction_time": transaction_time,
    }


def _c2b_account(shortcode):
    environment = getattr(settings, "MPESA_C2B_ENV", settings.MPESA_ENV)
    return MerchantTillAccount.objects.filter(
        shortcode=shortcode, environment=environment, is_active=True,
    ).first()


class C2BCallbackRateThrottle(AnonRateThrottle):
    scope = "mpesa_c2b_callback"


@api_view(["POST"])
@permission_classes([])
@throttle_classes([C2BCallbackRateThrottle])
def mpesa_c2b_validation(request, secret: str):
    """Safaricom C2B validation URL; rejects unconfigured or malformed receipts."""
    expected_secret = getattr(settings, "MPESA_C2B_CALLBACK_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise NotFound("Unknown callback address.")
    try:
        fields = _c2b_transaction_fields(request.data)
    except ValueError:
        return _c2b_response(1, "Rejected: invalid transaction details.")
    if not _c2b_account(fields["shortcode"]):
        return _c2b_response(1, "Rejected: merchant shortcode is not configured.")
    return _c2b_response()


@api_view(["POST"])
@permission_classes([])
@throttle_classes([C2BCallbackRateThrottle])
def mpesa_c2b_confirmation(request, secret: str):
    """Persist verified C2B confirmation before acknowledging Safaricom."""
    expected_secret = getattr(settings, "MPESA_C2B_CALLBACK_SECRET", "")
    if not expected_secret or secret != expected_secret:
        raise NotFound("Unknown callback address.")
    try:
        fields = _c2b_transaction_fields(request.data)
    except ValueError:
        return _c2b_response(1, "Rejected: invalid transaction details.")
    account = _c2b_account(fields["shortcode"])
    if account is None:
        return _c2b_response(1, "Rejected: merchant shortcode is not configured.")

    payload = request.data
    try:
        with transaction.atomic():
            transaction_row, created = IncomingTillTransaction.objects.get_or_create(
                account=account,
                receipt_number=fields["receipt_number"],
                defaults={
                    "amount": fields["amount"],
                    "transaction_time": fields["transaction_time"],
                    "currency": "KES",
                    "payer_phone": str(payload.get("MSISDN") or "")[:32],
                    "payer_first_name": str(payload.get("FirstName") or "")[:80],
                    "payer_middle_name": str(payload.get("MiddleName") or "")[:80],
                    "payer_last_name": str(payload.get("LastName") or "")[:80],
                    "bill_reference": str(payload.get("BillRefNumber") or "")[:64],
                    "third_party_transaction_id": str(payload.get("ThirdPartyTransID") or "")[:64],
                    "raw_payload": payload,
                },
            )
            if not created and (
                transaction_row.amount != fields["amount"]
                or transaction_row.transaction_time != fields["transaction_time"]
            ):
                transaction_row.status = IncomingTillTransaction.Status.DUPLICATE_REVIEW
                transaction_row.save(update_fields=["status", "updated_at"])
                record_audit(
                    action="mpesa.till_duplicate_conflict",
                    entity_type="incoming_till_transaction",
                    entity_id=transaction_row.pk,
                    branch=account.branch,
                    after={"receipt_number": fields["receipt_number"], "shortcode": account.shortcode},
                )
    except IntegrityError:
        # A concurrent duplicate callback is already represented by the unique
        # (account, receipt_number) constraint. Safaricom retries are harmless.
        pass
    return _c2b_response()


def _mask_phone(value):
    digits = str(value or "")
    if len(digits) <= 4:
        return "••••" if digits else ""
    return f"{digits[:3]}••••{digits[-3:]}"


@api_view(["GET"])
def unmatched_till_transactions(request):
    """List unmatched incoming Till receipts scoped to the signed-in tenant."""
    user = request.user
    if not user_has_permission(user, "sales.view"):
        return Response({"detail": "You do not have permission to view sales."}, status=403)
    organization = getattr(user, "organization", None)
    if organization is None:
        return Response({"detail": "No organization is assigned to this account."}, status=403)

    queryset = IncomingTillTransaction.objects.select_related("account", "account__branch").filter(
        account__organization=organization,
        status=IncomingTillTransaction.Status.UNMATCHED,
        currency="KES",
    )
    branch_ids = list(user.branch_access.values_list("branch_id", flat=True))
    if branch_ids:
        queryset = queryset.filter(models.Q(account__branch__isnull=True) | models.Q(account__branch_id__in=branch_ids))
    sale_id = request.query_params.get("sale")
    if sale_id:
        try:
            sale = Sale.objects.get(pk=sale_id, organization=organization, status=Sale.Status.COMPLETED)
        except (Sale.DoesNotExist, ValueError):
            return Response({"detail": "Sale not found."}, status=404)
        if branch_ids and sale.branch_id and sale.branch_id not in branch_ids:
            return Response({"detail": "You do not have access to this sale's branch."}, status=403)
        queryset = queryset.filter(amount=outstanding_for(sale))
        if sale.branch_id:
            queryset = queryset.filter(models.Q(account__branch__isnull=True) | models.Q(account__branch_id=sale.branch_id))
    amount = request.query_params.get("amount")
    if amount:
        try:
            amount_decimal = Decimal(amount).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError):
            return Response({"detail": "Amount must be a valid KES amount."}, status=400)
        queryset = queryset.filter(amount=amount_decimal)

    rows = []
    for item in queryset.order_by("-transaction_time")[:100]:
        rows.append({
            "id": str(item.pk),
            "receipt_number": item.receipt_number,
            "amount": str(item.amount),
            "currency": item.currency,
            "transaction_time": item.transaction_time.isoformat(),
            "payer_phone": _mask_phone(item.payer_phone),
            "payer_name": " ".join(part for part in (item.payer_first_name, item.payer_middle_name, item.payer_last_name) if part),
            "bill_reference": item.bill_reference,
            "shortcode": item.account.shortcode,
            "branch": item.account.branch.name if item.account.branch_id else None,
            "status": item.status,
        })
    return Response({"results": rows, "count": len(rows)})


@api_view(["POST"])
def match_till_transaction(request):
    """Atomically assign one confirmed incoming receipt to one eligible sale."""
    transaction_id = request.data.get("transaction_id")
    sale_id = request.data.get("sale_id")
    if not transaction_id or not sale_id:
        return Response({"detail": "transaction_id and sale_id are required."}, status=400)

    user = request.user
    organization = getattr(user, "organization", None)
    if organization is None:
        return Response({"detail": "No organization is assigned to this account."}, status=403)

    try:
        with transaction.atomic():
            try:
                sale = Sale.objects.select_for_update().get(
                    pk=sale_id, organization=organization, status=Sale.Status.COMPLETED,
                )
            except (Sale.DoesNotExist, ValueError):
                return Response({"detail": "Eligible sale not found."}, status=404)
            if not user_has_permission(user, "sales.create", branch_id=sale.branch_id):
                return Response({"detail": "You do not have permission to match payments for this sale."}, status=403)
            branch_ids = list(user.branch_access.values_list("branch_id", flat=True))
            if branch_ids and sale.branch_id and sale.branch_id not in branch_ids:
                return Response({"detail": "You do not have access to this sale's branch."}, status=403)

            try:
                incoming = IncomingTillTransaction.objects.select_for_update().select_related("account").get(
                    pk=transaction_id, account__organization=organization,
                )
            except (IncomingTillTransaction.DoesNotExist, ValueError):
                return Response({"detail": "Incoming Till transaction not found."}, status=404)

            if incoming.status != IncomingTillTransaction.Status.UNMATCHED:
                return Response({"detail": "This receipt has already been assigned or requires review."}, status=409)
            if incoming.currency != "KES" or incoming.amount <= 0:
                return Response({"detail": "Only positive KES transactions can be matched."}, status=400)
            if incoming.account.branch_id and incoming.account.branch_id != sale.branch_id:
                return Response({"detail": "The receipt belongs to a different branch."}, status=403)
            if branch_ids and incoming.account.branch_id and incoming.account.branch_id not in branch_ids:
                return Response({"detail": "You do not have access to this receipt's branch."}, status=403)

            outstanding = outstanding_for(sale)
            if outstanding <= 0 or incoming.amount > outstanding:
                return Response({"detail": f"Receipt amount must not exceed the outstanding balance of {outstanding}."}, status=400)
            if Payment.objects.filter(provider_reference=incoming.receipt_number).exclude(status=Payment.Status.REFUNDED).exists():
                incoming.status = IncomingTillTransaction.Status.DUPLICATE_REVIEW
                incoming.save(update_fields=["status", "updated_at"])
                return Response({"detail": "This M-Pesa receipt is already recorded on another payment and requires review."}, status=409)

            payment = Payment.objects.create(
                sale=sale,
                method=Payment.Method.MPESA,
                amount=incoming.amount,
                currency="KES",
                status=Payment.Status.COMPLETED,
                provider_reference=incoming.receipt_number,
                received_by=user,
            )
            incoming.status = IncomingTillTransaction.Status.MATCHED
            incoming.matched_sale = sale
            incoming.matched_payment = payment
            incoming.matched_by = user
            incoming.matched_at = timezone.now()
            incoming.save(update_fields=["status", "matched_sale", "matched_payment", "matched_by", "matched_at", "updated_at"])
            record_audit(
                action="payment.till_matched",
                entity_type="incoming_till_transaction",
                entity_id=incoming.pk,
                actor=user,
                request=request,
                branch=sale.branch,
                after={
                    "sale_id": str(sale.pk),
                    "payment_id": str(payment.pk),
                    "receipt_number": incoming.receipt_number,
                    "amount": str(incoming.amount),
                    "outstanding_after": str(outstanding - incoming.amount),
                },
            )
    except IntegrityError:
        return Response({"detail": "This receipt was matched by another request. Refresh and try again."}, status=409)

    return Response({
        "matched": True,
        "transaction_id": str(incoming.pk),
        "receipt_number": incoming.receipt_number,
        "payment_id": str(payment.pk),
        "sale_id": str(sale.pk),
        "amount": str(payment.amount),
        "outstanding_after": str(outstanding - payment.amount),
    }, status=200)
