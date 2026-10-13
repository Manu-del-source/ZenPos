"""API tests: the invoice surface is read-only and scoped through the sale.

The scoping tests build rows for *other* tenants and other branches the
normal way — through the real sales API — so what is being hidden is
genuinely there.
"""

import pytest
from rest_framework.test import APIClient

from modules.accounts.models import Role, User, UserRole
from modules.core.models import AuditLog
from modules.etims.models import EtimsInvoice
from modules.etims.services import issue_invoice_for_sale
from modules.inventory.models import BranchStock
from modules.sales.models import Sale

INVOICES_URL = "/api/v2/etims/invoices/"


def _cash_sale(client, items, **extra):
    """Create a cash sale through the real sales API and return it."""
    response = client.post(
        "/api/v2/sales/",
        {"payment_method": "CASH", "items": items, **extra},
        format="json",
    )
    assert response.status_code == 201, response.data
    return Sale.objects.get(pk=response.data["id"])


def _client_for(user):
    """A dedicated client for one user.

    The shared ``*_client`` fixtures all wrap the same underlying client, so a
    test that needs two *different* callers signed in builds the second one
    here instead of taking two fixtures.
    """
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestInvoiceReads:
    def test_invoice_list_and_retrieve(self, authenticated_client, product):
        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 2}])
        invoice = issue_invoice_for_sale(sale=sale)

        listed = authenticated_client.get(INVOICES_URL)

        assert listed.status_code == 200
        results = listed.data["results"]
        assert len(results) == 1
        assert results[0]["sale"] == sale.pk
        assert results[0]["sale_number"] == sale.sale_number
        assert results[0]["status"] == "ISSUED"
        assert results[0]["uin"] == ""
        # Money arrives as strings, at every level of the document.
        assert results[0]["total_amount"] == "200.00"
        assert results[0]["line_items"][0]["line_total"] == "200.00"
        assert results[0]["tax_breakdown"][0]["net"] == "200.00"

        retrieved = authenticated_client.get(f"{INVOICES_URL}{invoice.pk}/")

        assert retrieved.status_code == 200
        assert retrieved.data["sale"] == sale.pk
        assert retrieved.data["branch_name"] == "Westlands"

    def test_filter_by_sale(self, authenticated_client, product):
        first = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])
        second = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])
        first_invoice = issue_invoice_for_sale(sale=first)
        issue_invoice_for_sale(sale=second)

        response = authenticated_client.get(INVOICES_URL, {"sale": first.pk})

        assert response.status_code == 200
        results = response.data["results"]
        assert [row["sale"] for row in results] == [first_invoice.sale_id]


@pytest.mark.django_db
class TestInvoiceAuthorization:
    def test_requires_authentication(self, api_client):
        assert api_client.get(INVOICES_URL).status_code == 401

    def test_requires_the_sales_view_permission(self, db, api_client, organization):
        """A role without sales.view gets nothing, even though the table is
        joined through the sales domain it does own."""
        user = User.objects.create_user(
            username="invmgr",
            password="x",
            organization=organization,
        )
        # INVENTORY_MANAGER: products, stock, purchases — no sales.view.
        role = Role.objects.get(name="INVENTORY_MANAGER")
        UserRole.objects.create(user=user, role=role)
        api_client.force_authenticate(user=user)

        assert api_client.get(INVOICES_URL).status_code == 403

    def test_no_write_endpoints_exist(self, authenticated_client, product):
        """The API cannot create, edit or delete a compliance document."""
        assert authenticated_client.post(INVOICES_URL, {}, format="json").status_code == 405

        sale = _cash_sale(authenticated_client, [{"product": product.id, "quantity": 1}])
        invoice = issue_invoice_for_sale(sale=sale)
        detail_url = f"{INVOICES_URL}{invoice.pk}/"

        assert authenticated_client.put(detail_url, {}, format="json").status_code == 405
        assert authenticated_client.patch(detail_url, {}, format="json").status_code == 405
        assert authenticated_client.delete(detail_url).status_code == 405


@pytest.mark.django_db
class TestInvoiceIsolation:
    def test_organizations_cannot_see_each_others_invoices(
        self, cashier, product, foreign_product, rival_user
    ):
        own_client = _client_for(cashier)
        rival_client = _client_for(rival_user)
        own = _cash_sale(own_client, [{"product": product.id, "quantity": 1}])
        issue_invoice_for_sale(sale=own)
        rival_sale = _cash_sale(rival_client, [{"product": foreign_product.id, "quantity": 1}])
        issue_invoice_for_sale(sale=rival_sale)

        own_sales = [row["sale"] for row in own_client.get(INVOICES_URL).data["results"]]
        assert own_sales == [own.pk]
        rival_listed = rival_client.get(INVOICES_URL).data["results"]
        assert [row["sale"] for row in rival_listed] == [rival_sale.pk]

        # Retrieval is scoped too: the other tenant's id is a 404, not a
        # disclosure.
        rival_invoice = EtimsInvoice.objects.get(sale=rival_sale)
        assert own_client.get(f"{INVOICES_URL}{rival_invoice.pk}/").status_code == 404

    def test_branch_posted_cashier_sees_only_their_branch(
        self, cashier, manager, product, branch, other_branch
    ):
        """The cashier is posted to Westlands; the manager rings up a sale
        at the Karen branch. Same tenant — this proves the branch
        narrowing, not the tenant wall."""
        # Branch balances start at zero until a branch receives stock (phase
        # 7); seed both the way a receiving would, so the test is about
        # branch scoping and not about stock.
        for branch_row in (branch, other_branch):
            BranchStock.objects.create(
                organization=product.organization,
                branch=branch_row,
                product=product,
                quantity=10,
            )
        cashier_client = _client_for(cashier)
        manager_client = _client_for(manager)
        cashier_sale = _cash_sale(cashier_client, [{"product": product.id, "quantity": 1}])
        karen_sale = _cash_sale(
            manager_client,
            [{"product": product.id, "quantity": 1}],
            branch=other_branch.id,
        )
        assert cashier_sale.branch_id == branch.id
        assert karen_sale.branch_id == other_branch.id
        for sale in (cashier_sale, karen_sale):
            issue_invoice_for_sale(sale=sale)

        cashier_sales = [row["sale"] for row in cashier_client.get(INVOICES_URL).data["results"]]
        assert cashier_sales == [cashier_sale.pk]

        manager_sales = sorted(
            row["sale"] for row in manager_client.get(INVOICES_URL).data["results"]
        )
        assert manager_sales == sorted([cashier_sale.pk, karen_sale.pk])


@pytest.mark.django_db
class TestVoidCancelsTheInvoice:
    """The money path and the compliance path cannot drift: voiding a sale
    cancels its invoice in the same change the cash leaves the drawer."""

    def test_voiding_a_sale_cancels_its_invoice(self, cashier, product, supervisor):
        sale = _cash_sale(_client_for(cashier), [{"product": product.id, "quantity": 2}])
        invoice = issue_invoice_for_sale(sale=sale)

        response = _client_for(supervisor).post(
            f"/api/v2/sales/{sale.pk}/void/", {"reason": "Wrong item rung"}, format="json"
        )

        assert response.status_code == 200, response.data
        sale.refresh_from_db()
        assert sale.status == Sale.Status.VOIDED

        invoice.refresh_from_db()
        assert invoice.status == EtimsInvoice.Status.CANCELLED
        assert invoice.cancellation_reason == "Wrong item rung"
        assert invoice.cancelled_at is not None
        # The document is kept for reconciliation.
        assert invoice.total_amount == sale.total_amount

        assert AuditLog.objects.filter(action="etims.invoice_cancelled").count() == 1

    def test_voiding_a_sale_without_an_invoice_is_unaffected(self, cashier, product, supervisor):
        sale = _cash_sale(_client_for(cashier), [{"product": product.id, "quantity": 1}])

        response = _client_for(supervisor).post(
            f"/api/v2/sales/{sale.pk}/void/", {"reason": "changed mind"}, format="json"
        )

        assert response.status_code == 200, response.data
        assert EtimsInvoice.objects.count() == 0
        assert AuditLog.objects.filter(action="etims.invoice_cancelled").count() == 0


@pytest.mark.django_db
class TestAdminSurface:
    def test_invoice_admin_allows_no_write_at_all(self, platform_admin):
        """The Django admin is held to the API's rule: a compliance document
        is written once, at issue, and corrected only by cancellation — even
        for a superuser."""
        from django.test import RequestFactory

        from modules.etims.admin import EtimsInvoiceAdmin

        request = RequestFactory().get("/")
        request.user = platform_admin
        admin_instance = EtimsInvoiceAdmin(model=EtimsInvoice, admin_site=None)
        assert admin_instance.has_add_permission(request) is False
        assert admin_instance.has_change_permission(request) is False
        assert admin_instance.has_delete_permission(request) is False
