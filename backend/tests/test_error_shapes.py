"""
Phase 0 — golden-master error envelope shapes (STEP 10 companion).

Consumers (frontend api.js and future API consumers) must be able to rely on
these exact envelopes until a later phase changes them deliberately.
"""
from helpers import assert_contract


def test_404_shape_for_unknown_route(client):
    resp = client.get("/api/definitely-not-a-route")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_404_shape_for_unknown_api_subresource(client):
    resp = client.get("/api/products/1/does-not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_403_shape_permission_denied(client):
    resp = client.delete("/api/products/1")  # no role param
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Permission denied. Admin only."}


def test_400_shape_detail_is_a_plain_string(client):
    resp = client.post(
        "/api/products/",
        json={"sku": "ES-1", "name": "A", "cost_price": 1, "price": 2, "stock": 1},
    )
    assert resp.status_code == 200
    dup = client.post(
        "/api/products/",
        json={"sku": "ES-1", "name": "B", "cost_price": 1, "price": 2, "stock": 1},
    )
    assert dup.status_code == 400
    body = dup.json()
    assert_contract(body, "error_detail.json")
    assert set(body.keys()) == {"detail"}


def test_422_shape_detail_is_a_list_of_error_objects(client):
    resp = client.post("/api/products/", json={"sku": "ES-2"})
    assert resp.status_code == 422
    body = resp.json()
    assert_contract(body, "error_validation.json")
    assert isinstance(body["detail"], list)
    first = body["detail"][0]
    # Pydantic v2 error object shape (golden master):
    assert set(first.keys()) == {"type", "loc", "msg", "input"}


def test_error_envelope_never_has_extra_keys(client):
    cases = [
        client.get("/api/definitely-not-a-route"),
        client.delete("/api/products/1"),
        client.post("/api/products/", json={}),
    ]
    for resp in cases:
        body = resp.json()
        assert set(body.keys()) == {"detail"}


def test_500_unhandled_error_is_plain_text_not_json(client):
    """Golden master: UNHANDLED production exceptions are NOT JSON.

    Starlette's error middleware answers 500 with the plain text body
    'Internal Server Error' (text/plain). Known example: the dashboard crash.
    Consumers must handle this non-JSON surface until a later phase adds
    consistent error handling.
    """
    resp = client.get("/api/reports/dashboard", params={"role": "admin"})
    assert resp.status_code == 500
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == "Internal Server Error"


def test_method_not_allowed_shape_is_the_detail_envelope(client):
    """Golden master: wrong-method hits on existing paths return 405 JSON."""
    resp = client.get("/api/products/1")  # only PUT/DELETE exist on this path
    assert resp.status_code == 405
    assert resp.json() == {"detail": "Method Not Allowed"}
