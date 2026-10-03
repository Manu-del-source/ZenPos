"""
Phase 0 — CHARACTERIZATION of the current M-Pesa boundary (STEP 9).

ALL PROVIDER INTERACTION IS STUBBED. No test in this suite may make a real
Safaricom/Daraja request: the autouse fixture in conftest.py blocks
backend.mpesa_api.requests.get/post, and these tests replace
backend.api.mpesa_client entirely with a fake.

CURRENT SURFACE (golden master):
    POST /api/realtime/mpesa/stkpush   raw dict -> {status: "STK_SENT",
                                                 mpesa_response: <provider json>}
    * request fields read: phoneNumber, amount  (POS.jsx also sends saleId —
      it is silently IGNORED; no sale linkage exists)
    * callback URL is the hardcoded placeholder "https://your-domain.com/mpesa-callback"
    * NO input validation, NO provider-error handling, NO persistence,
      NO callback endpoint, NO status/reconciliation endpoint.

Environment variable NAMES required by the production MpesaGateWay design
(values must never appear in code or logs): MPESA_CONSUMER_KEY,
MPESA_CONSUMER_SECRET, MPESA_SHORTCODE, MPESA_PASSKEY, MPESA_CALLBACK_URL.
The active backend currently uses its own hardcoded MPESA_CONFIG instead.
"""
import pytest

from helpers import assert_contract


class FakeMpesaClient:
    """Deterministic stand-in for backend.mpesa_api.MpesaGateWay."""

    def __init__(self):
        self.calls = []
        self.response = {
            "MerchantRequestID": "mock-merchant-req",
            "CheckoutRequestID": "mock-checkout-req",
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        }
        self.raise_error = None

    def stk_push(self, phone, amount, callback_url, account_ref="POS_System"):
        self.calls.append(
            {
                "phone": phone,
                "amount": amount,
                "callback_url": callback_url,
                "account_ref": account_ref,
            }
        )
        if self.raise_error is not None:
            raise self.raise_error
        return self.response


@pytest.fixture()
def fake_mpesa(monkeypatch):
    fake = FakeMpesaClient()
    monkeypatch.setattr("backend.api.mpesa_client", fake)
    return fake


def _pos_stkpush_payload(sale_id=42):
    """Field names exactly as POS.jsx sends them."""
    return {"phoneNumber": "254712345678", "amount": 1500, "saleId": sale_id}


# ---------------------------------------------------------------------------
# Happy path through the stub
# ---------------------------------------------------------------------------
def test_stkpush_current_success_contract(client, fake_mpesa):
    resp = client.post("/api/realtime/mpesa/stkpush", json=_pos_stkpush_payload())
    assert resp.status_code == 200
    body = resp.json()
    assert_contract(body, "mpesa_stkpush_response.json")
    assert body["status"] == "STK_SENT"
    assert body["mpesa_response"] == fake_mpesa.response


def test_stkpush_forwards_phone_and_amount_with_placeholder_callback(
    client, fake_mpesa
):
    resp = client.post("/api/realtime/mpesa/stkpush", json=_pos_stkpush_payload())
    assert resp.status_code == 200
    assert len(fake_mpesa.calls) == 1
    call = fake_mpesa.calls[0]
    assert call["phone"] == "254712345678"
    assert call["amount"] == 1500
    # KNOWN DEFECT: hardcoded placeholder callback URL in backend/api.py.
    assert call["callback_url"] == "https://your-domain.com/mpesa-callback"


def test_stkpush_sale_id_is_ignored_no_sale_linkage(client, fake_mpesa):
    """POS.jsx sends saleId; the API neither echoes nor stores it."""
    for sale_id in (1, 999, "not-an-id"):
        body = client.post(
            "/api/realtime/mpesa/stkpush",
            json=_pos_stkpush_payload(sale_id=sale_id),
        ).json()
        assert "sale" not in body["status"].lower()
        assert set(body.keys()) == {"status", "mpesa_response"}
    # No persisted transactions of any kind:
    assert client.get("/api/sales/").json() == []


# ---------------------------------------------------------------------------
# Validation / error handling gaps (pinned current behavior)
# ---------------------------------------------------------------------------
def test_stkpush_empty_body_currently_still_calls_provider(client, fake_mpesa):
    """KNOWN DEFECT pinned: raw dict body, no validation whatsoever."""
    resp = client.post("/api/realtime/mpesa/stkpush", json={})
    assert resp.status_code == 200
    assert fake_mpesa.calls[0]["phone"] is None
    assert fake_mpesa.calls[0]["amount"] is None


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 7): stkpush must validate phone/amount and "
    "return 422/400 for missing fields.",
    strict=False,
)
def test_stkpush_empty_body_should_be_rejected(client, fake_mpesa):
    resp = client.post("/api/realtime/mpesa/stkpush", json={})
    assert resp.status_code in (400, 422)


def test_stkpush_provider_error_payload_currently_returned_as_success(
    client, fake_mpesa
):
    """KNOWN DEFECT pinned: Daraja-style error json is wrapped in STK_SENT 200."""
    fake_mpesa.response = {"error": "provider rejected the request"}
    resp = client.post("/api/realtime/mpesa/stkpush", json=_pos_stkpush_payload())
    assert resp.status_code == 200
    assert resp.json()["status"] == "STK_SENT"


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 7): provider error responses must map to 4xx/5xx.",
    strict=False,
)
def test_stkpush_provider_error_should_be_a_failure(client, fake_mpesa):
    fake_mpesa.response = {"error": "provider rejected the request"}
    resp = client.post("/api/realtime/mpesa/stkpush", json=_pos_stkpush_payload())
    assert resp.status_code >= 400


def test_stkpush_provider_exception_becomes_unhandled_500(client, fake_mpesa):
    """Current behavior: provider crashes surface as an unhandled plain-text
    500 ('Internal Server Error'), not a JSON envelope."""
    fake_mpesa.raise_error = RuntimeError("simulated provider outage")
    resp = client.post("/api/realtime/mpesa/stkpush", json=_pos_stkpush_payload())
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == "Internal Server Error"


# ---------------------------------------------------------------------------
# Absences that Phase 7 must build (documented as 404s today)
# ---------------------------------------------------------------------------
def test_mpesa_callback_endpoint_currently_missing(client):
    for method, path in (
        ("POST", "/mpesa-callback"),
        ("POST", "/api/realtime/mpesa/callback"),
        ("POST", "/api/mpesa/callback"),
    ):
        resp = client.request(method, path, json={})
        assert resp.status_code == 404, path


def test_mpesa_status_endpoint_currently_missing(client, fake_mpesa):
    for path in (
        "/api/realtime/mpesa/status/mock-checkout-req",
        "/api/payments/status/1",
    ):
        assert client.get(path).status_code == 404


def test_no_payment_persistence_tables_in_current_schema(client, test_db):
    """Current schema has no payments/mpesa transaction tables at all."""
    import sqlite3

    conn = sqlite3.connect(test_db)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert "payments" not in tables
    assert "mpesa_transactions" not in tables
    assert "stock_movements" not in tables  # future ledger (Phase 5)


# ---------------------------------------------------------------------------
# Safety rails (harness guarantees + credentials hygiene)
# ---------------------------------------------------------------------------
def test_real_provider_client_is_never_used_without_the_stub(client):
    """The autouse network guard makes ANY real provider call fail loudly."""
    from backend import api as api_module

    with pytest.raises(AssertionError, match="external HTTP"):
        # The REAL (unstubbed) client would attempt requests.get -> guard trips.
        api_module.mpesa_client  # sanity: module attribute exists
        import backend.mpesa_api as m

        m.requests.get("https://sandbox.safaricom.co.ke/oauth/v1/generate")


def test_mpesa_config_exposes_variable_names_only():
    """Hygiene: config KEYS are part of the contract; values never asserted."""
    from backend import api as api_module

    assert set(api_module.MPESA_CONFIG.keys()) == {
        "consumer_key",
        "consumer_secret",
        "shortcode",
        "passkey",
    }
