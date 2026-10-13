"""snapshot() never copies a secret into an audit row.

Audit rows are readable by tenant staff with ``audit.view`` and by the
platform, so a password hash or an API key reaching the log is a credential
leak dressed up as an audit trail. The filter is unconditional: an explicit
field list cannot ask a sensitive column back.
"""

import pytest

from modules.core.audit import snapshot
from modules.etims.models import EtimsDevice

pytestmark = pytest.mark.django_db


def test_a_user_snapshot_never_carries_the_password_hash(cashier):
    data = snapshot(cashier)

    assert "password" not in data
    assert data["username"] == cashier.username


def test_an_explicit_field_list_cannot_ask_for_a_secret(cashier):
    data = snapshot(cashier, ("username", "password", "email"))

    assert data == {"username": cashier.username, "email": cashier.email}


def test_a_device_snapshot_never_carries_the_api_key(db, organization):
    device = EtimsDevice.objects.create(
        organization=organization,
        name="Till 1",
        kda_pin="00000000",
        device_number="12345678",
        api_key="a-kra-credential",
    )

    data = snapshot(device)

    assert "api_key" not in data
    assert data["name"] == "Till 1"
    assert data["device_number"] == "12345678"
