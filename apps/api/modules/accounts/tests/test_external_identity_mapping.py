import pytest
from django.db import IntegrityError, transaction


@pytest.mark.django_db
def test_existing_users_do_not_need_a_clerk_identity(cashier):
    assert cashier.clerk_user_id is None


@pytest.mark.django_db
def test_clerk_user_identity_is_unique(cashier, other_cashier):
    cashier.clerk_user_id = "user_clerk_identity_test"
    cashier.save(update_fields=["clerk_user_id"])

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            other_cashier.clerk_user_id = "user_clerk_identity_test"
            other_cashier.save(update_fields=["clerk_user_id"])


@pytest.mark.django_db
def test_existing_organizations_do_not_need_a_clerk_identity(organization):
    assert organization.clerk_organization_id is None


@pytest.mark.django_db
def test_clerk_organization_identity_is_unique(organization, other_organization):
    organization.clerk_organization_id = "org_clerk_identity_test"
    organization.save(update_fields=["clerk_organization_id"])

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            other_organization.clerk_organization_id = "org_clerk_identity_test"
            other_organization.save(update_fields=["clerk_organization_id"])
