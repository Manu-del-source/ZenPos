"""Shared test fixtures.

Fixtures create the smallest slice of data a test needs. Nothing here reaches
across module boundaries more than the domain itself does.

Users do not carry a role *column* any more (phase 3 replaced the old ``role``
string with real tables), so fixtures grant roles and branch postings through
``UserRole`` and ``UserBranchAccess``. The seeded system roles come from
``accounts/migrations/0003_seed_rbac.py`` and ``.../0004_...``, which run when
the test database is created — grant a role by name, not by hand-building it.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from modules.accounts.models import Role, User, UserBranchAccess, UserRole
from modules.branches.models import Branch, Till
from modules.catalog.models import Product, ProductBarcode
from modules.customers.models import Customer
from modules.organizations.models import Organization

TEST_PASSWORD = "test-password-1"


@pytest.fixture(autouse=True)
def clear_throttle_cache():
    """Throttling counts requests in the default cache, which outlives a test.

    Without this, the login-throttling test would poison every test that logs in
    after it.
    """
    cache.clear()
    yield
    cache.clear()


def _ensure_system_roles_seeded() -> None:
    """Re-run the RBAC data migrations if a transactional-test flush took them.

    A ``transaction=True`` test runs without a rolling-back transaction, and
    pytest-django flushes the database after it — TRUNCATEing the
    migration-seeded roles and permissions along with the test data. The next
    fixture that grants a role by name would then fail. Re-running the same
    data-migration functions that seeded the schema keeps fixtures
    position-independent; when the rows already exist this is one ``exists()``
    query and nothing is written.
    """
    from modules.accounts.models import Role

    if Role.objects.filter(organization__isnull=True, is_system=True).exists():
        return

    import importlib

    from django.apps import apps as django_apps

    seed_steps = (
        ("0003_seed_rbac", "seed_rbac"),
        ("0004_branches_view_permission", "grant_branch_view"),
        ("0005_audit_view_permission", "grant_audit_view"),
        ("0006_purchases_view_permission", "grant_purchases_view"),
        ("0007_purchases_approve_permission", "grant_purchases_approve"),
        ("0008_purchases_receive_permission", "grant_purchases_receive"),
        ("0009_returns_request_permission", "grant"),
        ("0011_till_cash_permissions", "grant_till_cash_permissions"),
        ("0012_expense_permissions", "grant_expense_permissions"),
    )
    for module_name, function_name in seed_steps:
        module = importlib.import_module(f"modules.accounts.migrations.{module_name}")
        getattr(module, function_name)(django_apps, None)


def system_role(name):
    """A seeded system role by name, re-seeding after a flush if necessary.

    Fixtures grant roles by name rather than hand-building them, so the role
    must always exist — even in a test position that follows a
    ``transaction=True`` test's flush.
    """
    _ensure_system_roles_seeded()
    return Role.objects.get(name=name, organization__isnull=True)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def login(api_client):
    """Sign in through the real token endpoint rather than forcing a user."""

    def _login(username, password=TEST_PASSWORD):
        return api_client.post(
            "/api/v2/auth/login/",
            {"username": username, "password": password},
            format="json",
        )

    return _login


# ---------------------------------------------------------------------------
# Tenancy
# ---------------------------------------------------------------------------


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="ZenPOS Demo Store", slug="zenpos-demo-store")


@pytest.fixture
def other_organization(db):
    """A second tenant, used to prove data does not leak between them."""
    return Organization.objects.create(name="Rival Retail", slug="rival")


@pytest.fixture
def branch(db, organization):
    return Branch.objects.create(organization=organization, name="Westlands", code="BR-001")


@pytest.fixture
def other_branch(db, organization):
    return Branch.objects.create(organization=organization, name="Karen", code="BR-002")


@pytest.fixture
def till(db, organization, branch):
    return Till.objects.create(organization=organization, branch=branch, name="Till 1")


@pytest.fixture
def foreign_branch(db, other_organization):
    """Same code as ``branch``, different organization: codes are per tenant."""
    return Branch.objects.create(organization=other_organization, name="Mombasa", code="BR-001")


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------


@pytest.fixture
def make_user(db, organization):
    """Build a staff account and optionally grant one seeded system role."""

    def _make_user(username, role=None, **extra):
        user = User.objects.create_user(
            username=username,
            password=TEST_PASSWORD,
            organization=organization,
            **extra,
        )
        if role is not None:
            granted_role = system_role(role)
            UserRole.objects.create(user=user, role=granted_role)
        return user

    return _make_user


@pytest.fixture
def cashier(make_user, branch):
    """A CASHIER posted to one branch, so branch narrowing applies."""
    user = make_user("cashier1", role="CASHIER")
    UserBranchAccess.objects.create(user=user, branch=branch, is_default=True)
    return user


@pytest.fixture
def other_cashier(make_user):
    return make_user("cashier2", role="CASHIER")


@pytest.fixture
def supervisor(make_user, branch):
    """A SUPERVISOR posted to one branch only."""
    user = make_user("supervisor1", role="SUPERVISOR")
    UserBranchAccess.objects.create(user=user, branch=branch)
    return user


@pytest.fixture
def manager(make_user):
    """A MANAGER with no branch postings: organization-wide, i.e. head office."""
    return make_user("manager1", role="MANAGER")


@pytest.fixture
def admin_user(make_user):
    return make_user("admin1", role="ADMIN", is_staff=True)


@pytest.fixture
def platform_admin(db):
    """Platform staff: a superuser belonging to no organization."""
    return User.objects.create_superuser(username="platform", password=TEST_PASSWORD)


@pytest.fixture
def authenticated_client(api_client, cashier):
    api_client.force_authenticate(user=cashier)
    return api_client


@pytest.fixture
def other_client(api_client, other_cashier):
    api_client.force_authenticate(user=other_cashier)
    return api_client


@pytest.fixture
def supervisor_client(api_client, supervisor):
    api_client.force_authenticate(user=supervisor)
    return api_client


@pytest.fixture
def manager_client(api_client, manager):
    api_client.force_authenticate(user=manager)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    api_client.force_authenticate(user=admin_user)
    return api_client


@pytest.fixture
def platform_client(api_client, platform_admin):
    api_client.force_authenticate(user=platform_admin)
    return api_client


@pytest.fixture
def rival_user(db, other_organization):
    """A MANAGER belonging to the *other* organization.

    Used to build rows that genuinely belong to another tenant, so a scoping
    test has something real to hide.
    """
    manager_role = system_role("MANAGER")
    user = User.objects.create_user(
        username="rival-manager",
        password=TEST_PASSWORD,
        organization=other_organization,
    )
    UserRole.objects.create(user=user, role=manager_role)
    return user


@pytest.fixture
def rival_client(api_client, rival_user):
    """The other organization's manager, signed in."""
    api_client.force_authenticate(user=rival_user)
    return api_client


# ---------------------------------------------------------------------------
# Catalogue and customers
# ---------------------------------------------------------------------------


@pytest.fixture
def product(db, organization):
    return Product.objects.create(
        organization=organization,
        name="Milk 1L",
        sku="MILK-1L",
        price="100.00",
        cost_price="80.00",
        stock_level=50,
    )


@pytest.fixture
def make_product(db, organization):
    """Build a catalogue product with specific pricing for one test.

    The default ``product`` fixture covers the common case; tests that need a
    particular price or tax band use this instead.
    """

    def _make_product(
        *,
        name="Test product",
        price="100.00",
        cost_price="80.00",
        tax_rate=None,
        organization=organization,
        stock_level=50,
        **extra,
    ):
        return Product.objects.create(
            organization=organization,
            name=name,
            sku=extra.pop("sku", "SKU-" + name.replace(" ", "-").upper()),
            price=price,
            cost_price=cost_price,
            tax_rate=tax_rate,
            stock_level=stock_level,
            **extra,
        )

    return _make_product


@pytest.fixture
def product_barcode(db, product):
    """Barcodes live in their own table since phase 3."""
    return ProductBarcode.objects.create(
        organization=product.organization,
        product=product,
        barcode="111111",
        is_primary=True,
    )


@pytest.fixture
def foreign_product(db, other_organization):
    return Product.objects.create(
        organization=other_organization,
        name="Rival Milk 1L",
        sku="RIVAL-MILK-1L",
        price="90.00",
        cost_price="70.00",
        stock_level=5,
    )


@pytest.fixture
def customer(db, organization):
    return Customer.objects.create(
        organization=organization,
        name="Jane Wanjiru",
        phone="0722000001",
    )
