"""Unit tests for the M-Pesa adapter.

The transport is stubbed; no test ever touches Safaricom.
"""

from decimal import Decimal

import pytest

from modules.payments.base import PaymentCallbackError, PaymentGatewayError, StkInitiation
from modules.payments.mpesa import MpesaProvider, mpesa_callback_url


class StubTransport:
    """A fake ``requests`` session with canned responses per URL."""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def _respond(self, url):
        self.calls.append(url)
        for prefix, response in self.responses.items():
            if url.startswith(prefix):
                return response
        raise AssertionError(f"Unexpected URL requested: {url}")

    def get(self, url, **kwargs):
        return self._respond(url)

    def post(self, url, **kwargs):
        return self._respond(url)


class StubResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError("No JSON")
        return self._json


TOKEN_URL = "https://sandbox.safaricom.co.ke/oauth"
STK_URL = "https://sandbox.safaricom.co.ke/mpesa/stkpush"
QUERY_URL = "https://sandbox.safaricom.co.ke/mpesa/stkpushquery"


def make_provider(transport) -> MpesaProvider:
    return MpesaProvider(
        consumer_key="key",
        consumer_secret="secret",
        shortcode="174379",
        passkey="passkey",
        callback_url="https://api.example.com/callbacks",
        environment="sandbox",
        callback_secret="s3cret",
        transport=transport,
    )


class FakePayment:
    """The adapter only needs ``amount`` and ``sale_id``."""

    amount = Decimal("123.45")
    sale_id = "sale-uuid-1"


def test_missing_credentials_raise_at_init():
    with pytest.raises(ValueError) as excinfo:
        MpesaProvider(
            consumer_key="",
            consumer_secret="secret",
            shortcode="174379",
            passkey="passkey",
            callback_url="https://api.example.com/callbacks",
        )
    assert "MPESA_CONSUMER_KEY" in str(excinfo.value)


def test_bad_environment_raises_at_init():
    with pytest.raises(ValueError):
        make_provider(StubTransport()).__class__(
            consumer_key="k",
            consumer_secret="s",
            shortcode="1",
            passkey="p",
            callback_url="https://api.example.com/callbacks",
            environment="staging",
        )


def test_callback_url_embeds_the_secret_segment():
    url = mpesa_callback_url("https://api.example.com/callbacks/", "s3cret")
    assert url == "https://api.example.com/callbacks/s3cret/"


def test_callback_url_rejects_a_relative_base():
    with pytest.raises(ValueError):
        mpesa_callback_url("/callbacks", "s3cret")


def test_initiate_success_rounds_to_whole_shillings():
    transport = StubTransport(
        {
            TOKEN_URL: StubResponse(json_data={"access_token": "tok"}),
            STK_URL: StubResponse(
                json_data={
                    "CheckoutRequestID": "ws_CO_1",
                    "MerchantRequestID": "mr-1",
                    "ResponseCode": "0",
                }
            ),
        }
    )
    provider = make_provider(transport)

    initiation = provider.initiate(payment=FakePayment(), phone="0722000000")

    assert isinstance(initiation, StkInitiation)
    assert initiation.checkout_request_id == "ws_CO_1"
    assert initiation.provider_amount == Decimal("123")
    # The password must never be stored in the payloads.
    assert initiation.request_payload["Password"] == "***redacted***"
    assert initiation.request_payload["Amount"] == 123
    assert initiation.request_payload["CallBackURL"].endswith("/s3cret/")


def test_initiate_refusal_raises_with_payloads():
    transport = StubTransport(
        {
            TOKEN_URL: StubResponse(json_data={"access_token": "tok"}),
            STK_URL: StubResponse(
                json_data={"errorCode": "500.001.1001", "errorMessage": "invalid phone"}
            ),
        }
    )
    provider = make_provider(transport)

    with pytest.raises(PaymentGatewayError) as excinfo:
        provider.initiate(payment=FakePayment(), phone="0722000000")
    assert "invalid phone" in str(excinfo.value)
    assert excinfo.value.request_payload
    assert excinfo.value.response_payload


def test_initiate_with_non_json_response_raises():
    transport = StubTransport(
        {
            TOKEN_URL: StubResponse(json_data={"access_token": "tok"}),
            STK_URL: StubResponse(status_code=502, text="<html>bad gateway</html>"),
        }
    )
    provider = make_provider(transport)

    with pytest.raises(PaymentGatewayError) as excinfo:
        provider.initiate(payment=FakePayment(), phone="0722000000")
    assert "non-JSON" in str(excinfo.value)


def test_query_returns_the_provider_body():
    transport = StubTransport(
        {
            TOKEN_URL: StubResponse(json_data={"access_token": "tok"}),
            QUERY_URL: StubResponse(json_data={"ResultCode": "0", "ResultDesc": "Success"}),
        }
    )
    provider = make_provider(transport)

    body = provider.query("ws_CO_1")
    assert body["ResultCode"] == "0"


def test_callback_success_is_parsed_with_the_receipt_number():
    provider = make_provider(StubTransport())
    payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "mr-1",
                "CheckoutRequestID": "ws_CO_1",
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Key": "Amount", "Value": 123.00},
                        {"Key": "MpesaReceiptNumber", "Value": "QK71HLN2X9"},
                        {"Key": "PhoneNumber", "Value": 254722000000},
                    ]
                },
            }
        }
    }

    callback = provider.handle_callback(payload)

    assert callback.success is True
    assert callback.checkout_request_id == "ws_CO_1"
    assert callback.provider_reference == "QK71HLN2X9"
    assert callback.external_id == "QK71HLN2X9"
    assert callback.amount == Decimal("123.00")


def test_callback_failure_is_parsed_without_a_receipt():
    provider = make_provider(StubTransport())
    payload = {
        "Body": {
            "stkCallback": {
                "CheckoutRequestID": "ws_CO_2",
                "ResultCode": 1032,
                "ResultDesc": "Request cancelled by user",
            }
        }
    }

    callback = provider.handle_callback(payload)

    assert callback.success is False
    assert callback.provider_reference == ""
    # The de-duplication id falls back to the checkout request id.
    assert callback.external_id == "ws_CO_2"


@pytest.mark.parametrize(
    "payload",
    [
        "not-a-dict",
        {"Body": {}},
        {"Body": {"stkCallback": {"CheckoutRequestID": "ws_CO_1"}}},
        {
            "Body": {
                "stkCallback": {"CheckoutRequestID": "ws_CO_1", "ResultCode": "zero"}
            }
        },
    ],
)
def test_malformed_callbacks_raise(payload):
    provider = make_provider(StubTransport())

    with pytest.raises(PaymentCallbackError):
        provider.handle_callback(payload)
