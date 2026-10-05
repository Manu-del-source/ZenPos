"""Audit log tests (ADR-0013).

The properties under test are the ones the log exists for: rows appear for the
security-and-money events, they appear *only* when the change commits, and
another organization can never read them.
"""

import pytest

from modules.core.audit import record_audit
from modules.core.models import AuditLog
from modules.sales.models import Sale

AUDIT_URL = "/api/v2/audit-logs/"
LOGIN_URL = "/api/v2/auth/login/"
USERS_URL = "/api/v2/users/"
ROLES_URL = "/api/v2/roles/"
BRANCHES_URL = "/api/v2/branches/"
ORGS_URL = "/api/v2/organizations/"
SALES_URL = "/api/v2/sales/"
ADJUSTMENTS_URL = "/api/v2/adjustments/"


@pytest.fixture
def accountant_client(api_client, make_user):
    """An ACCOUNTANT holds ``audit.view``; that is the point of the role here."""
    user = make_user("accountant1", role="ACCOUNTANT")
    api_client.force_authenticate(user=user)
    return api_client


def sale_payload(product, *, sale_number="SALE-1", quantity=2):
    return {
        "sale_number": sale_number,
        "payment_method": "CASH",
        "items": [{"product": product.id, "quantity": quantity}],
    }


@pytest.mark.django_db
class TestAuditRowsAreWritten:
    def test_a_role_change_is_recorded_with_before_and_after(self, manager_client):
        created = manager_client.post(ROLES_URL, {"name": "Night Manager"}, format="json")
        assert created.status_code == 201, created.data
        role_id = created.data["id"]

        url = f"{ROLES_URL}{role_id}/set-permissions/"
        first = manager_client.post(url, {"permission_codes": ["sales.view"]}, format="json")
        assert first.status_code == 200, first.data
        second = manager_client.post(url, {"permission_codes": []}, format="json")
        assert second.status_code == 200, second.data

        # Two replacements happened, so two rows: oldest first.
        rows = list(
            AuditLog.objects.filter(action="role.permissions_changed").order_by("created_at")
        )
        assert len(rows) == 2
        assert rows[0].entity_id == str(role_id)
        assert rows[0].before == {"permission_codes": []}
        assert rows[0].after == {"permission_codes": ["sales.view"]}
        assert rows[1].before == {"permission_codes": ["sales.view"]}
        assert rows[1].after == {"permission_codes": []}

        # The creation itself is audited too, and both rows name the actor.
        creation = AuditLog.objects.get(action="role.created")
        assert creation.after["name"] == "Night Manager"
        assert creation.actor.username == "manager1"

    def test_updating_a_user_records_a_shallow_diff(
        self, admin_client, other_cashier
    ):
        response = admin_client.patch(
            f"{USERS_URL}{other_cashier.id}/", {"first_name": "Anew"}, format="json"
        )

        assert response.status_code == 200, response.data

        row = AuditLog.objects.get(action="user.updated")
        assert row.before["first_name"] == ""
        assert row.after["first_name"] == "Anew"

    def test_a_password_reset_records_that_it_happened_and_nothing_else(
        self, manager_client, other_cashier
    ):
        response = manager_client.post(
            f"{USERS_URL}{other_cashier.id}/set-password/",
            {"password": "another-password-2"},
            format="json",
        )

        assert response.status_code == 200, response.data

        row = AuditLog.objects.get(action="user.password_reset")
        assert row.entity_id == str(other_cashier.id)
        flattened = str(row.before) + str(row.after)
        assert "another-password-2" not in flattened

    def test_completing_a_sale_records_the_money(self, authenticated_client, product):
        response = authenticated_client.post(SALES_URL, sale_payload(product), format="json")
        assert response.status_code == 201, response.data

        row = AuditLog.objects.get(action="sale.created")
        assert row.after["sale_number"].startswith("SALE-")
        assert row.after["total_amount"] == "200.00"
        assert row.actor.username == "cashier1"

        # The stock movement the sale caused is audited per product.
        movement = AuditLog.objects.get(action="stock.adjusted", entity_type="product")
        assert movement.after == {"stock_level": 48}

    def test_a_stock_adjustment_records_the_before_and_after(
        self, manager_client, product
    ):
        response = manager_client.post(
            ADJUSTMENTS_URL,
            {"product": product.id, "quantity": 5, "type": "RESTOCK", "notes": "top-up"},
            format="json",
        )
        assert response.status_code == 201, response.data

        row = AuditLog.objects.get(action="stock.adjusted")
        assert row.before == {"stock_level": 50}
        assert row.after == {"stock_level": 55}

    def test_organization_and_branch_changes_are_recorded(
        self, admin_client, manager_client, organization
    ):
        renamed = admin_client.patch(
            f"{ORGS_URL}{organization.id}/", {"name": "Kipchi Mart"}, format="json"
        )
        assert renamed.status_code == 200, renamed.data

        opened = manager_client.post(
            BRANCHES_URL,
            {"name": "Kilimani", "code": "BR-003"},
            format="json",
        )
        assert opened.status_code == 201, opened.data

        assert AuditLog.objects.filter(action="organization.updated").count() == 1
        branch_row = AuditLog.objects.get(action="branch.created")
        assert branch_row.after["name"] == "Kilimani"
        assert branch_row.branch.name == "Kilimani"

    def test_a_successful_api_login_is_recorded(self, api_client, manager):
        response = api_client.post(
            LOGIN_URL,
            {"username": "manager1", "password": "test-password-1"},
            format="json",
        )

        assert response.status_code == 200, response.data

        row = AuditLog.objects.get(action="auth.login")
        assert row.actor_id == manager.id
        assert row.ip_address == "127.0.0.1"

    def test_a_failed_login_is_recorded_with_the_attempted_username(self, api_client):
        response = api_client.post(
            LOGIN_URL,
            {"username": "ghost-user", "password": "wrong-password-1"},
            format="json",
        )

        assert response.status_code == 401

        row = AuditLog.objects.get(action="auth.login_failed")
        assert row.actor is None
        assert row.attempted_username == "ghost-user"
        assert row.ip_address == "127.0.0.1"


@pytest.mark.django_db
class TestAuditRowsRollBackWithTheirChange:
    def test_a_failed_sale_leaves_no_audit_rows(
        self, authenticated_client, product, make_product
    ):
        """The audit row is inside the transaction, so a rollback takes it back.

        The first line's ``stock.adjusted`` row is written before the second
        line fails its stock check — if the log were written after commit, or
        on a signal, that row would survive the rollback and describe a sale
        that never happened.
        """
        scarce = make_product(name="Scarce item", stock_level=1, price="50.00")
        payload = sale_payload(product, sale_number="SALE-FAIL")
        payload["items"].append({"product": scarce.id, "quantity": 5})

        response = authenticated_client.post(SALES_URL, payload, format="json")

        assert response.status_code == 400
        assert Sale.objects.count() == 0
        assert AuditLog.objects.count() == 0

        product.refresh_from_db()
        assert product.stock_level == 50


@pytest.mark.django_db
class TestAuditAccess:
    def test_reading_requires_audit_view(self, authenticated_client, manager):
        record_audit(
            action="sale.created",
            entity_type="sale",
            actor=manager,
            after={"total_amount": "10.00"},
        )

        response = authenticated_client.get(AUDIT_URL)

        assert response.status_code == 403
        assert AuditLog.objects.count() == 1

    def test_an_accountant_can_read_the_log(self, accountant_client, manager):
        record_audit(
            action="sale.created",
            entity_type="sale",
            actor=manager,
            after={"total_amount": "10.00"},
        )

        response = accountant_client.get(AUDIT_URL)

        assert response.status_code == 200
        assert response.data["count"] == 1
        assert response.data["results"][0]["actor_name"] == "manager1"

    def test_another_organizations_rows_are_invisible(
        self, admin_client, rival_user
    ):
        record_audit(
            action="sale.created",
            entity_type="sale",
            actor=rival_user,
            after={"total_amount": "10.00"},
        )

        response = admin_client.get(AUDIT_URL)

        assert response.status_code == 200
        assert response.data["count"] == 0

    def test_failed_logins_of_the_organization_are_visible_but_rivals_are_not(
        self, admin_client, other_cashier
    ):
        """A failed login has no actor; the tenant is the attempted username."""
        ours = record_audit(
            action="auth.login_failed",
            entity_type="user",
            attempted_username=other_cashier.username,
        )
        record_audit(
            action="auth.login_failed",
            entity_type="user",
            attempted_username="rival-manager",
        )

        response = admin_client.get(AUDIT_URL)

        assert response.status_code == 200
        ids = {row["id"] for row in response.data["results"]}
        assert str(ours.id) in ids
        assert len(ids) == 1

    def test_platform_staff_see_every_row(self, platform_client, manager, rival_user):
        record_audit(action="sale.created", entity_type="sale", actor=manager)
        record_audit(action="sale.created", entity_type="sale", actor=rival_user)

        response = platform_client.get(AUDIT_URL)

        assert response.status_code == 200
        assert response.data["count"] == 2
