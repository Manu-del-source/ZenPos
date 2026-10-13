"""Shared fixtures for the payments test suite.

``stub_provider`` patches the provider in *both* namespaces the module is
imported from — the views (initiation, callbacks) and the services
(settle/reap) — so no test path can reach the real provider construction or
the network. A test module may shadow this with a local fixture of the same
name (test_payments_api.py does, with a different default amount).
"""

from decimal import Decimal
from unittest import mock

import pytest

from modules.branches.services import open_cash_session
from modules.payments.base import StkInitiation


@pytest.fixture
def stub_provider():
    """A provider whose initiation always succeeds; callbacks are injectable.

    The default initiation amount is one shilling, so a callback test must
    say what amount the provider actually charged: set
    ``stub_provider.initiate.return_value`` (or the callback's amount) to the
    number under test. The callback handler matches the reported amount
    against the attempt's recorded amount, and a silent default is how the
    "1.00 charged, 200.00 reported" mistake sneaks in.
    """
    with mock.patch(
        "modules.payments.views.get_payment_provider"
    ) as getter, mock.patch(
        "modules.payments.services.get_payment_provider", getter
    ):
        provider = mock.Mock()
        provider.provider_name = "MPESA"
        provider.initiate.return_value = StkInitiation(
            checkout_request_id="ws_SPLIT_OK",
            merchant_request_id="mr-split",
            provider_amount=Decimal("1"),
            request_payload={"Amount": 1},
            response_payload={"CheckoutRequestID": "ws_SPLIT_OK"},
        )
        getter.return_value = provider
        yield provider


@pytest.fixture
def open_session(cashier, till):
    """A shift already open at the till, so drawer movements have a home."""
    return open_cash_session(
        till=till, actor=cashier, opening_cash=Decimal("1000.00"), request=None
    )
