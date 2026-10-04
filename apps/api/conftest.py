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
from modules.branches.models import Branch
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
    return Organization.objects.create(name="Kipchi Supermarket", slug="kipchi")


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
            system_role = Role.objects.get(name=role, organization__isnull=True)
            UserRole.objects.create(user=user, role=system_role)
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
    role = Role.objects.get(name="MANAGER", organization__isnull=True)
    user = User.objects.create_user(
        username="rival-manager",
        password=TEST_PASSWORD,
        organization=other_organization,
    )
    UserRole.objects.create(user=user, role=role)
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
