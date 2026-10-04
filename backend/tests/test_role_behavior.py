"""Phase 1 authorization contracts: roles are derived from persisted users."""
from helpers import create_product


def test_protected_routes_reject_missing_credentials(anonymous_client):
    routes = [
        ("GET", "/api/products/"),
        ("POST", "/api/products/"),
        ("GET", "/api/customers/"),
        ("GET", "/api/sales/"),
        ("POST", "/api/sales/"),
        ("POST", "/api/realtime/mpesa/stkpush"),
        ("GET", "/api/reports/dashboard"),
    ]
    for method, path in routes:
        response = anonymous_client.request(method, path, json={} if method == "POST" else None)
        assert response.status_code == 401, (method, path, response.text)


def test_cashier_cannot_use_admin_product_routes(cashier_client):
    response = cashier_client.post(
        "/api/products/",
        json={"sku": "CASHIER-1", "name": "No", "cost_price": 1, "price": 2, "stock": 1},
    )
    assert response.status_code == 403
    assert cashier_client.get("/api/reports/dashboard").status_code == 403


def test_query_role_cannot_grant_admin_access(anonymous_client):
    response = anonymous_client.delete("/api/products/1", params={"role": "admin"})
    assert response.status_code == 401
    response = anonymous_client.get("/api/reports/dashboard", params={"role": "admin"})
    assert response.status_code == 401


def test_cashier_query_role_cannot_override_admin_identity(client):
    product = create_product(client, sku="ROLE-OVERRIDE")
    response = client.delete(
        f"/api/products/{product['id']}", params={"role": "cashier"}
    )
    assert response.status_code == 200


def test_admin_can_use_admin_product_routes(client):
    product = create_product(client, sku="ADMIN-DELETE")
    response = client.delete(f"/api/products/{product['id']}")
    assert response.status_code == 200


def test_role_is_reloaded_from_database_for_each_request(cashier_client, test_db):
    import sqlite3

    token = cashier_client.headers["Authorization"]
    conn = sqlite3.connect(test_db)
    try:
        conn.execute(
            "INSERT INTO products (sku, name, cost_price, price, stock) VALUES (?, ?, ?, ?, ?)",
            ("DB-ROLE", "Role check", 1, 2, 1),
        )
        product_id = conn.execute("SELECT id FROM products WHERE sku='DB-ROLE'").fetchone()[0]
        conn.execute("UPDATE users SET role='admin' WHERE username='cashier'")
        conn.commit()
    finally:
        conn.close()
    response = cashier_client.delete(
        f"/api/products/{product_id}", headers={"Authorization": token}
    )
    assert response.status_code == 200
