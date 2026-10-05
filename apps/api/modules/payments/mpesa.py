"""M-Pesa STK-push adapter (Safaricom Daraja), behind ``PaymentProvider``.

Ported from ``legacy/backend/src/services/mpesa.service.js`` where the port was
worth keeping: the timestamp/password construction, the STK status query and
the pending-payment de-duplication idea. The de-duplication itself lives in the
service layer (``assert_no_pending_stk``) because it is a business rule about
payments, not a property of Safaricom's API.

The adapter does not know about ``Payment`` rows, attempts or idempotency — it
moves bytes to and from Safaricom. Everything it needs is handed in; secrets
come from the environment (ADR-0005) and a missing one raises here at
construction time, not mid-request.

``requests`` is the transport and is injectable for tests: no test ever touches
Safaricom.
"""

import base64
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from urllib.parse import urlparse

import requests

from .base import (
    PaymentCallbackError,
    PaymentGatewayError,
    PaymentProvider,
    ProviderCallback,
    StkInitiation,
)

SANDBOX_BASE_URL = "https://sandbox.safaricom.co.ke"
PRODUCTION_BASE_URL = "https://api.safaricom.co.ke"

#: STK push charges whole shillings only — the rounding is recorded on the
#: attempt row so reconciliation can explain the one-shilling difference.
SHILLING = Decimal("1")

# Values Safaricom sends back that are derived from our own credentials; they
# are redacted from stored payloads rather than duplicated into the database.
REDACTED_KEYS = frozenset({"Password", "access_token"})
REDACTED = "***redacted***"


def _redact(payload: dict) -> dict:
    return {key: (REDACTED if key in REDACTED_KEYS else value) for key, value in payload.items()}


def mpesa_callback_url(base_callback_url: str, callback_secret: str) -> str:
    """The full callback URL, with the secret path segment embedded.

    Safaricom signs nothing (ADR-0012), so the unguessable secret segment is
    the first trust filter: a forged callback that has not learned the URL is
    rejected before any code parses its body.
    """
    parsed = urlparse(base_callback_url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("MPESA_CALLBACK_URL must be an absolute http(s) URL.")
    path = parsed.path.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}{path}/{callback_secret}/"


class MpesaProvider(PaymentProvider):
    provider_name = "MPESA"

    def __init__(
        self,
        *,
        consumer_key: str,
        consumer_secret: str,
        shortcode: str,
        passkey: str,
        callback_url: str,
        environment: str = "sandbox",
        callback_secret: str = "",
        timeout_seconds: int = 15,
        transport=None,
    ):
        missing = [
            name
            for name, value in (
                ("MPESA_CONSUMER_KEY", consumer_key),
                ("MPESA_CONSUMER_SECRET", consumer_secret),
                ("MPESA_SHORTCODE", shortcode),
                ("MPESA_PASSKEY", passkey),
                ("MPESA_CALLBACK_URL", callback_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"M-Pesa credentials are missing from the environment: {', '.join(missing)}."
            )
        if environment not in {"sandbox", "production"}:
            raise ValueError(f"MPESA_ENV must be 'sandbox' or 'production', not {environment!r}.")

        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.shortcode = shortcode
        self.passkey = passkey
        self.base_url = SANDBOX_BASE_URL if environment == "sandbox" else PRODUCTION_BASE_URL
        self.callback_secret = callback_secret
        self.callback_url = mpesa_callback_url(callback_url, callback_secret)
        self.timeout_seconds = timeout_seconds
        self._transport = transport or requests

    # -- plumbing -----------------------------------------------------------

    def _token(self) -> str:
        auth = base64.b64encode(f"{self.consumer_key}:{self.consumer_secret}".encode()).decode()
        try:
            response = self._transport.get(
                f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials",
                headers={"Authorization": f"Basic {auth}"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise PaymentGatewayError(f"M-Pesa token request failed: {exc}") from exc
        if response.status_code != 200:
            raise PaymentGatewayError(
                f"M-Pesa token request returned {response.status_code}.",
                response_payload={
                    "status_code": response.status_code,
                    "body": response.text[:2000],
                },
            )
        token = response.json().get("access_token")
        if not token:
            raise PaymentGatewayError("M-Pesa token response contained no access_token.")
        return token

    def _post(self, path: str, payload: dict, token: str) -> dict:
        try:
            response = self._transport.post(
                f"{self.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise PaymentGatewayError(
                f"M-Pesa request to {path} failed: {exc}",
                request_payload=_redact(payload),
            ) from exc
        try:
            body = response.json()
        except ValueError:
            raise PaymentGatewayError(
                f"M-Pesa returned non-JSON from {path} (HTTP {response.status_code}).",
                request_payload=_redact(payload),
                response_payload={
                    "status_code": response.status_code,
                    "body": response.text[:2000],
                },
            ) from None
        if response.status_code != 200:
            raise PaymentGatewayError(
                f"M-Pesa request to {path} returned {response.status_code}.",
                request_payload=_redact(payload),
                response_payload=body,
            )
        return body

    def _timestamp_and_password(self) -> tuple[str, str]:
        from django.utils import timezone

        timestamp = timezone.localtime().strftime("%Y%m%d%H%M%S")
        password = base64.b64encode(f"{self.shortcode}{self.passkey}{timestamp}".encode()).decode()
        return timestamp, password

    # -- PaymentProvider ----------------------------------------------------

    def initiate(self, *, payment, phone: str) -> StkInitiation:
        """Ask Safaricom to push an STK prompt to the customer's phone.

        Returns what Safaricom offered (request ids), not money: completion
        arrives only through the callback. The amount sent is rounded to whole
        shillings; the exact amount stays on the payment.
        """
        token = self._token()
        timestamp, password = self._timestamp_and_password()
        provider_amount = payment.amount.quantize(SHILLING, rounding=ROUND_HALF_UP)

        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(provider_amount),
            "PartyA": phone,
            "PartyB": self.shortcode,
            "PhoneNumber": phone,
            "CallBackURL": self.callback_url,
            "AccountReference": f"SALE-{payment.sale_id}",
            "TransactionDesc": "ZenPOS payment",
        }
        body = self._post("/mpesa/stkpush/v1/processrequest", payload, token)

        checkout_request_id = body.get("CheckoutRequestID", "")
        if not checkout_request_id:
            # Safaricom also reports failures as HTTP 200 with an errorCode;
            # treat anything without a request id as a refusal.
            refusal = body.get("errorMessage", "no CheckoutRequestID returned.")
            raise PaymentGatewayError(
                f"M-Pesa STK push was refused: {refusal}",
                request_payload=_redact(payload),
                response_payload=body,
            )

        return StkInitiation(
            checkout_request_id=checkout_request_id,
            merchant_request_id=body.get("MerchantRequestID", ""),
            provider_amount=provider_amount,
            request_payload=_redact(payload),
            response_payload=body,
        )

    def query(self, checkout_request_id: str) -> dict:
        """Ask Safaricom for the status of one STK request."""
        token = self._token()
        timestamp, password = self._timestamp_and_password()
        payload = {
            "BusinessShortCode": self.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }
        return self._post("/mpesa/stkpushquery/v1/query", payload, token)

    def handle_callback(self, payload) -> ProviderCallback:
        """Normalize an STK callback body, or raise ``PaymentCallbackError``.

        Success is read from Safaricom's own result code, never taken on trust:
        the caller still has to match the ``CheckoutRequestID`` against a
        PENDING attempt we issued before anything is marked COMPLETED.
        """
        if not isinstance(payload, dict):
            raise PaymentCallbackError("Callback body must be a JSON object.")

        body = payload.get("Body") or {}
        stk_callback = body.get("stkCallback") or {}
        checkout_request_id = stk_callback.get("CheckoutRequestID", "")
        result_code = stk_callback.get("ResultCode")
        if not checkout_request_id or result_code is None:
            raise PaymentCallbackError("Callback is missing CheckoutRequestID or ResultCode.")

        try:
            code = int(result_code)
        except (TypeError, ValueError):
            raise PaymentCallbackError(f"Unreadable ResultCode {result_code!r}.") from None

        callback_items = stk_callback.get("CallbackMetadata", {}).get("Item", []) or []
        metadata = {}
        for item in callback_items:
            if "Key" in item and "Value" in item:
                metadata[item["Key"]] = item["Value"]

        amount = None
        if "Amount" in metadata:
            try:
                amount = Decimal(str(metadata["Amount"])).quantize(Decimal("0.01"))
            except InvalidOperation:
                amount = None

        return ProviderCallback(
            checkout_request_id=checkout_request_id,
            success=code == 0,
            provider_reference=str(metadata.get("MpesaReceiptNumber", "")),
            external_id=str(metadata.get("MpesaReceiptNumber") or checkout_request_id),
            result_desc=str(stk_callback.get("ResultDesc", "")),
            amount=amount,
        )
