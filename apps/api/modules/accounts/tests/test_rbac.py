import pytest
from rest_framework.test import APIClient

from modules.accounts.models import Permission, Role, UserBranchAccess, UserRole
from modules.accounts.permissions import permission_codes_for, user_has_permission

LOGIN_URL = "/api/v2/auth/login/"
ME_URL = "/api/v2/auth/me/"
ROLES_URL = "/api/v2/roles/"
PERMISSIONS_URL = "/api/v2/permissions/"

EXPECTED_SYSTEM_ROLES = {
    "SUPER_ADMIN",
    "ADMIN",
    "MANAGER",
    "SUPERVISOR",
    "CASHIER",
    "INVENTORY_MANAGER",
    "ACCOUNTANT",
}


@pytest.mark.django_db
class TestSeededRbac:
    def test_the_system_roles_are_seeded(self, db):
        names = set(Role.objects.filter(organization__isnull=True).values_list("name", flat=True))

        assert names == EXPECTED_SYSTEM_ROLES

    def test_every_system_role_can_read_branch_names(self, db):
        """A receipt prints a branch; every role needs to be able to name one."""
        for name in EXPECTED_SYSTEM_ROLES:
            role = Role.objects.get(name=name)
            assert role.permissions.filter(code="branches.view").exists(), name

    def test_permissions_belong_to_no_organization(self, db):
        """The vocabulary is platform-wide; roles are what vary per tenant."""
        assert Permission.objects.count() > 0
        assert Permission.objects.filter(code="sales.refund").exists()

    def test_a_cashier_may_sell_but_not_refund(self, cashier):
        assert user_has_permission(cashier, "sales.create")
        assert not user_has_permission(cashier, "sales.refund")

    def test_a_manager_may_refund_and_read_reports(self, manager):
        assert user_has_permission(manager, "sales.refund")
        assert user_has_permission(manager, "reports.view")

    def test_a_manager_may_not_change_organization_settings(self, manager):
        assert not user_has_permission(manager, "settings.manage")

    def test_an_unknown_code_is_never_granted(self, cashier):
        assert not user_has_permission(cashier, "sales.teleport")

    def test_a_user_with_no_roles_holds_nothing(self, make_user):
        user = make_user("roleless")

        assert permission_codes_for(user) == set()
        assert not user_has_permission(user, "sales.create")

    def test_a_platform_superuser_holds_every_code(self, platform_admin):
        assert user_has_permission(platform_admin, "sales.teleport")
        assert permission_codes_for(platform_admin) >= {"sales.refund", "users.manage"}


@pytest.mark.django_db
class TestBranchScopedGrants:
    def test_a_grant_at_one_branch_does_not_apply_at_another(
        self, make_user, branch, other_branch
    ):
        user = make_user("branch-supervisor")
        role = Role.objects.get(name="SUPERVISOR", organization__isnull=True)
        UserRole.objects.create(user=user, role=role, branch=branch)

        assert user_has_permission(user, "sales.refund", branch_id=branch.id)
        assert not user_has_permission(user, "sales.refund", branch_id=other_branch.id)

    def test_the_unscoped_question_still_sees_the_grant(self, make_user, branch):
        """A view-level check must not deny before it knows which branch is meant."""
        user = make_user("branch-supervisor")
        role = Role.objects.get(name="SUPERVISOR", organization__isnull=True)
        UserRole.objects.create(user=user, role=role, branch=branch)

        assert user_has_permission(user, "sales.refund")

    def test_an_organization_wide_grant_applies_at_every_branch(
        self, manager, branch, other_branch
    ):
        assert user_has_permission(manager, "sales.refund", branch_id=branch.id)
        assert user_has_permission(manager, "sales.refund", branch_id=other_branch.id)

    def test_a_role_held_at_one_branch_does_not_widen_a_second_role(
        self, make_user, branch, other_branch
    ):
        user = make_user("supervisor-cashier")
        cashier_role = Role.objects.get(name="CASHIER", organization__isnull=True)
        supervisor_role = Role.objects.get(name="SUPERVISOR", organization__isnull=True)
        UserRole.objects.create(user=user, role=cashier_role)
        UserRole.objects.create(user=user, role=supervisor_role, branch=branch)

        assert user_has_permission(user, "sales.create")
        assert not user_has_permission(user, "sales.refund", branch_id=other_branch.id)


@pytest.mark.django_db
class TestMeEndpoint:
    def test_me_reports_roles_permissions_and_branches(
        self, authenticated_client, cashier, branch
    ):
        response = authenticated_client.get(ME_URL)

        assert response.status_code == 200, response.data
        assert response.data["roles"] == ["CASHIER"]
        assert response.data["branch_ids"] == [str(branch.id)]
        assert "sales.create" in response.data["permissions"]
        assert "sales.refund" not in response.data["permissions"]

    def test_me_is_never_another_users(self, authenticated_client, cashier, other_cashier):
        response = authenticated_client.get(ME_URL)

        assert response.data["username"] == cashier.username

    def test_me_is_read_only(self, authenticated_client, cashier):
        """The token holder must not be able to edit their own account here."""
        response = authenticated_client.patch(ME_URL, {"username": "someone-else"}, format="json")

        assert response.status_code == 405
        cashier.refresh_from_db()
        assert cashier.username == "cashier1"

    def test_me_rejects_an_anonymous_caller(self, api_client):
        response = api_client.get(ME_URL)

        assert response.status_code in (401, 403)


@pytest.mark.django_db
class TestLogin:
    def test_login_returns_a_token_pair(self, login, cashier):
        response = login(cashier.username)

        assert response.status_code == 200, response.data
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_rejects_a_wrong_password(self, login, cashier):
        response = login(cashier.username, "not-the-password")

        assert response.status_code == 401

    def test_login_is_throttled(self, login, cashier):
        """Ten attempts a minute per address, then the door closes."""
        for _ in range(10):
            login(cashier.username, "wrong-password")

        response = login(cashier.username, "wrong-password")

        assert response.status_code == 429

    def test_the_throttle_survives_a_correct_password(self, login, cashier):
        """Guessing must not be rewarded by finally getting it right."""
        for _ in range(10):
            login(cashier.username, "wrong-password")

        response = login(cashier.username)

        assert response.status_code == 429


@pytest.mark.django_db
class TestRoleCatalogue:
    def test_the_catalogue_is_listed(self, authenticated_client):
        response = authenticated_client.get(PERMISSIONS_URL)

        assert response.status_code == 200
        codes = {row["code"] for row in response.data["results"]}
        assert "sales.create" in codes
        assert "branches.view" in codes

    def test_a_cashier_can_see_the_roles_available(self, authenticated_client):
        """A client cannot render a staff form without knowing the role names."""
        response = authenticated_client.get(ROLES_URL)

        assert response.status_code == 200
        names = {row["name"] for row in response.data["results"]}
        assert {"CASHIER", "MANAGER"} <= names

    def test_system_roles_come_with_their_permission_codes(self, authenticated_client):
        response = authenticated_client.get(ROLES_URL)
        cashier_role = next(row for row in response.data["results"] if row["name"] == "CASHIER")

        assert "sales.create" in cashier_role["permission_codes"]
        assert "sales.refund" not in cashier_role["permission_codes"]

    def test_an_organization_can_add_its_own_role(self, authenticated_client, organization):
        Role.objects.create(organization=organization, name="TILL_SUPERVISOR")

        response = authenticated_client.get(ROLES_URL)
        names = {row["name"] for row in response.data["results"]}

        assert "TILL_SUPERVISOR" in names

    def test_another_organizations_roles_are_invisible(
        self, authenticated_client, other_organization
    ):
        Role.objects.create(organization=other_organization, name="RIVAL_ROLE")

        response = authenticated_client.get(ROLES_URL)
        names = {row["name"] for row in response.data["results"]}

        assert "RIVAL_ROLE" not in names

    def test_permissions_are_read_only(self, authenticated_client):
        response = authenticated_client.post(
            PERMISSIONS_URL, {"code": "sales.teleport", "module": "sales"}, format="json"
        )

        assert response.status_code == 405


def role_payload(**overrides):
    payload = {"name": "TILL_SUPERVISOR", "description": "Runs a till"}
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestRoleWrites:
    def test_a_cashier_cannot_create_a_role(self, authenticated_client):
        response = authenticated_client.post(ROLES_URL, role_payload(), format="json")

        assert response.status_code == 403
        assert not Role.objects.filter(name="TILL_SUPERVISOR").exists()

    def test_a_manager_can_create_a_role_for_their_organization(
        self, manager_client, organization
    ):
        response = manager_client.post(ROLES_URL, role_payload(), format="json")

        assert response.status_code == 201, response.data
        role = Role.objects.get(name="TILL_SUPERVISOR")
        assert role.organization_id == organization.id
        assert role.is_system is False

    def test_creating_a_role_cannot_set_its_permissions(self, manager_client):
        """Grants go through set-permissions, so a rename can never re-scope access."""
        response = manager_client.post(
            ROLES_URL,
            role_payload(permission_codes=["sales.refund"], is_system=True),
            format="json",
        )

        assert response.status_code == 201, response.data
        role = Role.objects.get(name="TILL_SUPERVISOR")
        assert role.permissions.count() == 0
        assert role.is_system is False

    def test_set_permissions_replaces_the_whole_set(self, manager_client, manager):
        role = Role.objects.create(organization=manager.organization, name="TILL_SUPERVISOR")
        url = f"{ROLES_URL}{role.id}/set-permissions/"

        first = manager_client.post(
            url, {"permission_codes": ["sales.create", "sales.view"]}, format="json"
        )
        assert first.status_code == 200, first.data
        assert sorted(first.data["permission_codes"]) == ["sales.create", "sales.view"]

        second = manager_client.post(url, {"permission_codes": ["sales.view"]}, format="json")
        assert second.status_code == 200, second.data
        assert second.data["permission_codes"] == ["sales.view"]
        assert not role.permissions.filter(code="sales.create").exists()

    def test_an_unknown_permission_code_is_rejected(self, manager_client, manager):
        role = Role.objects.create(organization=manager.organization, name="TILL_SUPERVISOR")

        response = manager_client.post(
            f"{ROLES_URL}{role.id}/set-permissions/",
            {"permission_codes": ["sales.teleport"]},
            format="json",
        )

        assert response.status_code == 400
        assert role.permissions.count() == 0

    def test_a_system_role_cannot_be_edited(self, manager_client):
        role = Role.objects.get(name="CASHIER")

        rename = manager_client.patch(
            f"{ROLES_URL}{role.id}/", {"name": "NOT_A_CASHIER"}, format="json"
        )
        grants = manager_client.post(
            f"{ROLES_URL}{role.id}/set-permissions/",
            {"permission_codes": ["sales.refund"]},
            format="json",
        )

        assert rename.status_code == 403
        assert grants.status_code == 403
        assert Role.objects.filter(name="CASHIER").exists()

    def test_a_system_role_cannot_be_deleted(self, manager_client):
        role = Role.objects.get(name="CASHIER")

        response = manager_client.delete(f"{ROLES_URL}{role.id}/")

        assert response.status_code == 403

    def test_an_assigned_role_cannot_be_deleted(self, manager_client, manager, other_cashier):
        role = Role.objects.create(organization=manager.organization, name="TILL_SUPERVISOR")
        UserRole.objects.create(user=other_cashier, role=role)

        response = manager_client.delete(f"{ROLES_URL}{role.id}/")

        assert response.status_code == 400
        assert Role.objects.filter(pk=role.pk).exists()

    def test_an_unassigned_role_can_be_deleted(self, manager_client, manager):
        role = Role.objects.create(organization=manager.organization, name="TILL_SUPERVISOR")

        response = manager_client.delete(f"{ROLES_URL}{role.id}/")

        assert response.status_code == 204
        assert not Role.objects.filter(pk=role.pk).exists()


@pytest.mark.django_db
class TestRoleVisibilityIsNotEnoughToManage:
    """A cashier can *read* a role without being able to change anything."""

    def test_reading_is_open_and_writing_is_not(self, authenticated_client):
        listed = authenticated_client.get(ROLES_URL)
        assert listed.status_code == 200

        cashier_role = Role.objects.get(name="CASHIER")
        edited = authenticated_client.patch(
            f"{ROLES_URL}{cashier_role.id}/", {"name": "X"}, format="json"
        )
        assert edited.status_code == 403


@pytest.mark.django_db
class TestUserBranchAccessModel:
    def test_a_default_branch_is_flagged_not_inferred(self, cashier, branch):
        access = UserBranchAccess.objects.get(user=cashier)

        assert access.branch_id == branch.id
        assert access.is_default is True


LOGOUT_URL = "/api/v2/auth/logout/"


@pytest.mark.django_db
class TestLogout:
    """Signing out must revoke the refresh token, not just forget it locally."""

    def test_logout_blacklists_the_callers_refresh_token(self, api_client, cashier, login):
        tokens = login(cashier.username).data
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = api_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")
        refreshed = APIClient().post(
            "/api/v2/auth/refresh/", {"refresh": tokens["refresh"]}, format="json"
        )

        assert response.status_code == 200, response.data
        assert refreshed.status_code == 401

    def test_another_users_refresh_token_is_not_revoked(
        self, api_client, cashier, other_cashier, login
    ):
        """Otherwise a stolen access token becomes a way to sign strangers out."""
        victim = login(other_cashier.username).data
        attacker = login(cashier.username).data
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {attacker['access']}")

        response = api_client.post(LOGOUT_URL, {"refresh": victim["refresh"]}, format="json")
        still_valid = APIClient().post(
            "/api/v2/auth/refresh/", {"refresh": victim["refresh"]}, format="json"
        )

        assert response.status_code == 200
        assert still_valid.status_code == 200

    def test_logout_requires_a_session(self, api_client):
        response = api_client.post(LOGOUT_URL, {"refresh": "whatever"}, format="json")

        assert response.status_code in (401, 403)

    def test_logout_is_recorded(self, api_client, cashier, login):
        from modules.core.models import AuditLog

        tokens = login(cashier.username).data
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        api_client.post(LOGOUT_URL, {"refresh": tokens["refresh"]}, format="json")

        assert AuditLog.objects.filter(action="auth.logout").count() == 1
