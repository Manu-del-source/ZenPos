"""The payment provider interface (ADR-0012).

Every payment adapter implements ``PaymentProvider``. The sales domain records
*that* a payment succeeded — never *how* — so M-Pesa, card and (in phase 8)
eTIMS adapters slot in behind this interface without the sales domain ever
learning a provider's vocabulary.

Adapters raise, they do not return error codes:

- ``PaymentGatewayError`` — the provider was reachable and refused, or could
  not be reached at all. Carries the request/response payloads of the failed
  exchange when it has them, so the attempt row can record what happened.
- ``PaymentCallbackError`` — a callback payload that cannot be parsed into a
  result. The caller must not store it as a webhook event with success
  semantics.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal


class PaymentError(Exception):
    """Base class for every payment-provider failure."""


class PaymentGatewayError(PaymentError):
    """A provider exchange failed: refused, unreachable, or unparseable."""

    def __init__(
        self,
        message: str,
        *,
        request_payload: dict | None = None,
        response_payload: dict | None = None,
    ):
        super().__init__(message)
        self.request_payload = request_payload
        self.response_payload = response_payload


class PaymentCallbackError(PaymentError):
    """A callback payload that cannot be trusted or understood."""


@dataclass(frozen=True)
class StkInitiation:
    """The result of asking a provider to start a customer payment."""

    checkout_request_id: str
    merchant_request_id: str
    # What was actually sent to the provider, which can differ from the
    # payment's amount (M-Pesa STK push charges whole shillings only).
    provider_amount: Decimal
    # The full exchange, with secrets redacted, for the attempt row.
    request_payload: dict = field(default_factory=dict)
    response_payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderCallback:
    """A parsed callback, normalized across providers."""

    checkout_request_id: str
    success: bool
    # The provider's receipt number, when the payment succeeded.
    provider_reference: str = ""
    # The id this callback is de-duplicated on in ``webhook_events``.
    external_id: str = ""
    result_desc: str = ""
    amount: Decimal | None = None


class PaymentProvider(ABC):
    """The interface the rest of the system is written against."""

    #: Short name stored on payments, attempts and webhook events.
    provider_name: str = ""

    @abstractmethod
    def initiate(self, *, payment, phone: str) -> StkInitiation:
        """Ask the provider to charge the customer. Returns the offer, not the
        money: completion always arrives through a callback."""

    @abstractmethod
    def query(self, checkout_request_id: str) -> dict:
        """Ask the provider for the status of one in-flight request."""

    @abstractmethod
    def handle_callback(self, payload) -> ProviderCallback:
        """Normalize one callback payload, or raise ``PaymentCallbackError``."""
