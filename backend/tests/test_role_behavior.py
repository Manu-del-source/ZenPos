"""
Phase 0 — CROSS-CUTTING characterization of the current 'role' mechanism
(STEP 10 companion).

CURRENT MECHANISM (golden master): authorization is a CLIENT-SUPPLIED query
parameter `role`, compared case-insensitively to the literal 'admin'. There is
no session, no token parsing, no server-side identity. Any caller can pass
role=admin. This module pins that behavior so Phase 2 (real RBAC) must change
it deliberately, with these tests updated in the same change.
"""
import pytest

from helpers import create_product


def test_role_is_a_query_param_not_a_header(client):
    """DELETE denies without ?role= even with an 'admin' Authorization header."""
    product = create_product(client, sku="RB-1")
    resp = client.delete(
        f"/api/products/{product['id']}",
        headers={"Authorization": "Bearer anything", "X-Role": "admin"},
    )
    assert resp.status_code == 403


def test_role_param_spoofing_grants_admin_today(client):
    """KNOWN DEFECT (Phase 2): 'role=admin' is taken at face value."""
    product = create_product(client, sku="RB-2")
    resp = client.delete(f"/api/products/{product['id']}", params={"role": "admin"})
    assert resp.status_code == 200


def test_role_value_comparison_is_case_insensitive_lowercase_only_matters(client):
    product = create_product(client, sku="RB-3")
    for value in ("admin", "ADMIN", "Admin", "aDmIn"):
        p = create_product(client, sku=f"RB-3-{value}")
        resp = client.delete(f"/api/products/{p['id']}", params={"role": value})
        assert resp.status_code == 200, value


def test_role_arbitrary_strings_are_not_admin(client):
    product = create_product(client, sku="RB-4")
    for value in ("superuser", "root", "manager", "administrator", ""):
        resp = client.delete(
            f"/api/products/{product['id']}", params={"role": value}
        )
        assert resp.status_code == 403, value


def test_dashboard_role_param_spoofing_grants_access_to_the_gate(client):
    """role=admin passes the dashboard gate (then crashes — separate defect)."""
    resp = client.get("/api/reports/dashboard", params={"role": "admin"})
    assert resp.status_code != 403  # gate passed; 500 is the known crash


@pytest.mark.xfail(
    reason="KNOWN DEFECT (Phase 2): authorization must come from a verified "
    "identity, not a spoofable query parameter.",
    strict=False,
)
def test_role_param_spoofing_should_not_grant_admin(client):
    product = create_product(client, sku="RB-5")
    resp = client.delete(f"/api/products/{product['id']}", params={"role": "admin"})
    assert resp.status_code in (401, 403)
