"""Expenses: append-only money-out ledger.

Covers the behaviours the reporting layer will lean on: tenant and branch
scoping, RBAC, server-stamped audit fields, append-only semantics (no
update/delete), and the reversal rule that replaces edits.

Multi-user tests build a fresh ``APIClient`` per user (``client_for``): the
shared ``api_client`` fixtures all re-authenticate one object, so two of them
in one test would leave the later one winning for both names.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from modules.accounts.models import UserBranchAccess
from modules.core.models import AuditLog
from modules.expenses.models import Expense, ExpenseCategory

EXPENSE_URL = "/api/v2/expenses/"
CATEGORY_URL = "/api/v2/expense-categories/"


@pytest.fixture
def client_for():
    def _client_for(user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    return _client_for


@pytest.fixture
def accountant(make_user):
    """An ACCOUNTANT with no branch postings: organisation-wide."""
    return make_user("accountant1", role="ACCOUNTANT")


@pytest.fixture
def branch_manager(make_user, branch):
    """A MANAGER posted to one branch only, for branch-access tests."""
    user = make_user("branch-manager1", role="MANAGER")
    UserBranchAccess.objects.create(user=user, branch=branch)
    return user


@pytest.fixture
def other_branch_manager(make_user, other_branch):
    """A MANAGER posted to the *other* branch only."""
    user = make_user("other-branch-manager1", role="MANAGER")
    UserBranchAccess.objects.create(user=user, branch=other_branch)
    return user


@pytest.fixture
def category(db, organization):
    return ExpenseCategory.objects.create(organization=organization, name="Rent")


@pytest.fixture
def other_category(db, organization):
    return ExpenseCategory.objects.create(organization=organization, name="Utilities")


@pytest.fixture
def expense(db, organization, branch, category, cashier):
    return Expense.objects.create(
        organization=organization,
        branch=branch,
        category=category,
        expense_number="EXP-TEST-0001",
        date=timezone.localdate(),
        amount=Decimal("500.00"),
        created_by=cashier,
    )


@pytest.fixture
def expense_payload(branch, category):
    return {
        "branch": str(branch.pk),
        "category": str(category.pk),
        "date": "2026-10-12",
        "amount": "1250.50",
        "reference": "RECEIPT-88",
        "notes": "Generator fuel",
    }


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


class TestExpenseCategories:
    def test_create_stamps_organisation(self, manager_client, organization):
        response = manager_client.post(CATEGORY_URL, {"name": "Wages"}, format="json")
        assert response.status_code == 201, response.data
        created = ExpenseCategory.objects.get(name="Wages")
        assert created.organization_id == organization.pk

    def test_names_unique_per_organisation(
        self, manager_client, organization, other_organization, category
    ):
        # Same name in a different tenant is fine...
        ExpenseCategory.objects.create(organization=other_organization, name="Rent")
        # ...but a duplicate inside the tenant is not.
        response = manager_client.post(CATEGORY_URL, {"name": "Rent"}, format="json")
        assert response.status_code == 400
        assert "name" in response.data

    def test_cashier_cannot_manage_categories(self, authenticated_client):
        response = authenticated_client.post(CATEGORY_URL, {"name": "Wages"}, format="json")
        assert response.status_code == 403

    def test_rival_sees_only_own_categories(self, rival_client, other_organization, category):
        ExpenseCategory.objects.create(organization=other_organization, name="Rival Rent")
        response = rival_client.get(CATEGORY_URL)
        assert response.status_code == 200
        assert [row["name"] for row in response.data["results"]] == ["Rival Rent"]

    def test_category_with_expenses_cannot_be_deleted(self, manager_client, expense, category):
        response = manager_client.delete(f"{CATEGORY_URL}{category.pk}/")
        assert response.status_code == 400
        assert ExpenseCategory.objects.filter(pk=category.pk).exists()

    def test_deactivating_category_blocks_new_expenses(
        self, manager_client, branch_manager, expense_payload, client_for
    ):
        category = expense_payload["category"]
        ExpenseCategory.objects.filter(pk=category).update(is_active=False)
        response = client_for(branch_manager).post(EXPENSE_URL, expense_payload, format="json")
        assert response.status_code == 400
        assert "category" in response.data


# ---------------------------------------------------------------------------
# Creating expenses
# ---------------------------------------------------------------------------


class TestExpenseCreate:
    def test_create_stamps_server_fields(
        self, manager_client, manager, organization, expense_payload
    ):
        response = manager_client.post(EXPENSE_URL, expense_payload, format="json")
        assert response.status_code == 201, response.data
        saved = Expense.objects.get(pk=response.json()["id"])
        assert saved.expense_number.startswith("EXP-")
        assert saved.organization_id == organization.pk
        assert saved.created_by_id == manager.pk
        assert saved.amount == Decimal("1250.50")
        assert response.json()["amount"] == "1250.50"

    def test_cashier_cannot_create_expense(self, authenticated_client, expense_payload):
        response = authenticated_client.post(EXPENSE_URL, expense_payload, format="json")
        assert response.status_code == 403

    def test_expense_cannot_be_created_in_unposted_branch(
        self, branch_manager, other_branch, category, client_for
    ):
        payload = {
            "branch": str(other_branch.pk),
            "category": str(category.pk),
            "date": "2026-10-12",
            "amount": "10.00",
        }
        response = client_for(branch_manager).post(EXPENSE_URL, payload, format="json")
        assert response.status_code == 403

    def test_expense_with_foreign_organisation_branch_rejected(
        self, manager_client, other_organization, foreign_branch, category
    ):
        payload = {
            "branch": str(foreign_branch.pk),
            "category": str(category.pk),
            "date": "2026-10-12",
            "amount": "10.00",
        }
        response = manager_client.post(EXPENSE_URL, payload, format="json")
        assert response.status_code == 400
        assert "branch" in response.data

    def test_expense_with_foreign_organisation_category_rejected(
        self, manager_client, other_organization, branch, category
    ):
        rival_category = ExpenseCategory.objects.create(
            organization=other_organization, name="Rent"
        )
        payload = {
            "branch": str(branch.pk),
            "category": str(rival_category.pk),
            "date": "2026-10-12",
            "amount": "10.00",
        }
        response = manager_client.post(EXPENSE_URL, payload, format="json")
        assert response.status_code == 400
        assert "category" in response.data

    def test_nonpositive_amount_rejected(self, manager_client, expense_payload):
        for bad in ("0.00", "-50.00"):
            payload = dict(expense_payload, amount=bad)
            response = manager_client.post(EXPENSE_URL, payload, format="json")
            assert response.status_code == 400, bad

    def test_create_is_audited(self, manager_client, expense_payload, branch):
        response = manager_client.post(EXPENSE_URL, expense_payload, format="json")
        assert response.status_code == 201
        row = AuditLog.objects.get(action="expense.created")
        assert row.entity_id == response.json()["id"]
        assert row.branch_id == branch.pk


# ---------------------------------------------------------------------------
# Reading: scoping
# ---------------------------------------------------------------------------


class TestExpenseScoping:
    def test_branch_posted_user_sees_only_own_branch(
        self, supervisor, other_branch, category, cashier, client_for, expense
    ):
        Expense.objects.create(
            organization=supervisor.organization,
            branch=other_branch,
            category=category,
            expense_number="EXP-TEST-0002",
            date=timezone.localdate(),
            amount=Decimal("10.00"),
            created_by=cashier,
        )
        response = client_for(supervisor).get(EXPENSE_URL)
        assert response.status_code == 200
        assert [row["expense_number"] for row in response.data["results"]] == ["EXP-TEST-0001"]

    def test_head_office_sees_all_branches(
        self, manager_client, other_branch, category, cashier, expense
    ):
        Expense.objects.create(
            organization=cashier.organization,
            branch=other_branch,
            category=category,
            expense_number="EXP-TEST-0003",
            date=timezone.localdate(),
            amount=Decimal("10.00"),
            created_by=cashier,
        )
        response = manager_client.get(EXPENSE_URL)
        assert response.status_code == 200
        numbers = {row["expense_number"] for row in response.data["results"]}
        assert {"EXP-TEST-0001", "EXP-TEST-0003"} <= numbers

    def test_rival_cannot_read_expense(self, rival_client, expense):
        assert rival_client.get(EXPENSE_URL).data["results"] == []
        assert rival_client.get(f"{EXPENSE_URL}{expense.pk}/").status_code == 404

    def test_list_filters_by_date_and_category(
        self, manager_client, other_branch, other_category, cashier, expense
    ):
        Expense.objects.create(
            organization=cashier.organization,
            branch=other_branch,
            category=other_category,
            expense_number="EXP-TEST-0004",
            date=timezone.localdate() - timezone.timedelta(days=30),
            amount=Decimal("10.00"),
            created_by=cashier,
        )
        response = manager_client.get(EXPENSE_URL, {"date_from": "2026-10-01"})
        assert [row["expense_number"] for row in response.data["results"]] == ["EXP-TEST-0001"]
        response = manager_client.get(EXPENSE_URL, {"category": str(other_category.pk)})
        assert [row["expense_number"] for row in response.data["results"]] == ["EXP-TEST-0004"]


# ---------------------------------------------------------------------------
# Append-only
# ---------------------------------------------------------------------------


class TestAppendOnly:
    def test_update_forbidden(self, manager_client, expense):
        response = manager_client.patch(
            f"{EXPENSE_URL}{expense.pk}/", {"amount": "1.00"}, format="json"
        )
        assert response.status_code == 405
        assert expense.amount == Decimal("500.00")

    def test_delete_forbidden(self, manager_client, expense):
        response = manager_client.delete(f"{EXPENSE_URL}{expense.pk}/")
        assert response.status_code == 405
        assert Expense.objects.filter(pk=expense.pk).exists()


# ---------------------------------------------------------------------------
# Reversals
# ---------------------------------------------------------------------------


class TestReversal:
    def test_reverse_appends_a_reversal_row(self, manager_client, expense, branch, category):
        response = manager_client.post(f"{EXPENSE_URL}{expense.pk}/reverse/")
        assert response.status_code == 201, response.data
        reversal = Expense.objects.get(pk=response.json()["id"])
        assert reversal.reversal_of_id == expense.pk
        assert reversal.amount == expense.amount
        assert reversal.date == expense.date
        assert reversal.branch_id == branch.pk
        assert reversal.category_id == category.pk
        assert reversal.is_reversal
        assert f"Reversal of {expense.expense_number}" in reversal.notes
        # The original row is byte-for-byte untouched.
        original = Expense.objects.get(pk=expense.pk)
        assert original.amount == Decimal("500.00")
        assert original.reversal_of is None

    def test_cannot_reverse_twice(self, manager_client, expense):
        first = manager_client.post(f"{EXPENSE_URL}{expense.pk}/reverse/")
        assert first.status_code == 201
        second = manager_client.post(f"{EXPENSE_URL}{expense.pk}/reverse/")
        assert second.status_code == 400
        assert "already been reversed" in str(second.data)

    def test_cannot_reverse_a_reversal(self, manager_client, expense):
        reversal = Expense.objects.create(
            organization=expense.organization,
            branch=expense.branch,
            category=expense.category,
            expense_number="EXP-TEST-REVSRC",
            date=timezone.localdate(),
            amount=expense.amount,
            created_by=expense.created_by,
            reversal_of=expense,
        )
        response = manager_client.post(f"{EXPENSE_URL}{reversal.pk}/reverse/")
        assert response.status_code == 400

    def test_cashier_cannot_reverse(self, authenticated_client, expense):
        response = authenticated_client.post(f"{EXPENSE_URL}{expense.pk}/reverse/")
        assert response.status_code == 403

    def test_reversal_outside_branch_is_not_found(
        self, other_branch_manager, client_for, expense
    ):
        response = client_for(other_branch_manager).post(
            f"{EXPENSE_URL}{expense.pk}/reverse/"
        )
        assert response.status_code == 404

    def test_reverse_is_audited(self, manager_client, expense, branch):
        response = manager_client.post(f"{EXPENSE_URL}{expense.pk}/reverse/")
        assert response.status_code == 201
        row = AuditLog.objects.get(action="expense.reversed")
        assert row.entity_id == response.json()["id"]
        assert row.branch_id == branch.pk
