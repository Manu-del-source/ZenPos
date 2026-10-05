import pytest

from modules.accounts.models import Role, User, UserBranchAccess, UserRole
from modules.accounts.permissions import user_has_permission

USERS_URL = "/api/v2/users/"


def user_payload(**overrides):
    payload = {"username": "cashier9", "password": "strong-password-9"}
    payload.update(overrides)
    return payload


@pytest.mark.django_db
class TestWhoMayManageStaff:
    def test_a_cashier_cannot_list_staff(self, authenticated_client):
        response = authenticated_client.get(USERS_URL)

        assert response.status_code == 403

    def test_a_supervisor_cannot_list_staff(self, supervisor_client):
        response = supervisor_client.get(USERS_URL)

        assert response.status_code == 403

    def test_a_manager_can_list_their_own_staff(self, manager_client, cashier):
        response = manager_client.get(USERS_URL)

        assert response.status_code == 200, response.data
        usernames = {row["username"] for row in response.data["results"]}
        assert "manager1" in usernames
        assert "cashier1" in usernames

    def test_another_organizations_staff_are_never_listed(self, manager_client, rival_user):
        response = manager_client.get(USERS_URL)

        usernames = {row["username"] for row in response.data["results"]}
        assert rival_user.username not in usernames

    def test_another_organizations_staff_are_a_404_not_a_403(self, manager_client, rival_user):
        """A 403 would confirm the account exists."""
        response = manager_client.get(f"{USERS_URL}{rival_user.id}/")

        assert response.status_code == 404


@pytest.mark.django_db
class TestStaffCreation:
    def test_a_manager_creates_a_cashier(self, manager_client, organization):
        response = manager_client.post(USERS_URL, user_payload(), format="json")

        assert response.status_code == 201, response.data
        assert response.data["organization"] == str(organization.id)
        assert response.data["roles"] == []

        created = User.objects.get(username="cashier9")
        assert created.organization_id == organization.id
        assert created.is_staff is False
        assert created.is_superuser is False
        assert created.check_password("strong-password-9")

    def test_the_client_cannot_choose_the_organization(
        self, manager_client, organization, other_organization
    ):
        response = manager_client.post(
            USERS_URL,
            user_payload(organization=str(other_organization.id)),
            format="json",
        )

        assert response.status_code == 201, response.data
        assert User.objects.get(username="cashier9").organization_id == organization.id

    def test_the_client_cannot_mint_a_superuser(self, manager_client):
        response = manager_client.post(
            USERS_URL,
            user_payload(username="root", is_superuser=True, is_staff=True),
            format="json",
        )

        assert response.status_code == 201, response.data
        created = User.objects.get(username="root")
        assert created.is_superuser is False
        assert created.is_staff is False

    def test_a_password_is_required(self, manager_client):
        response = manager_client.post(USERS_URL, {"username": "cashier9"}, format="json")

        assert response.status_code == 400
        assert "password" in response.data

    def test_a_weak_password_is_rejected(self, manager_client):
        response = manager_client.post(
            USERS_URL, user_payload(username="cashier9", password="123"), format="json"
        )

        assert response.status_code == 400
        assert not User.objects.filter(username="cashier9").exists()

    def test_a_duplicate_username_is_rejected(self, manager_client, cashier):
        response = manager_client.post(
            USERS_URL, user_payload(username=cashier.username), format="json"
        )

        assert response.status_code == 400

    def test_a_default_branch_must_be_in_the_callers_organization(
        self, manager_client, foreign_branch
    ):
        response = manager_client.post(
            USERS_URL, user_payload(default_branch=str(foreign_branch.id)), format="json"
        )

        assert response.status_code == 400
        assert "default_branch" in response.data


@pytest.mark.django_db
class TestStaffUpdates:
    def test_a_manager_can_rename_a_cashier(self, manager_client, other_cashier):
        response = manager_client.patch(
            f"{USERS_URL}{other_cashier.id}/", {"first_name": "Brian"}, format="json"
        )

        assert response.status_code == 200, response.data
        other_cashier.refresh_from_db()
        assert other_cashier.first_name == "Brian"

    def test_a_manager_can_deactivate_a_cashier(self, manager_client, other_cashier):
        response = manager_client.patch(
            f"{USERS_URL}{other_cashier.id}/", {"is_active": False}, format="json"
        )

        assert response.status_code == 200, response.data
        other_cashier.refresh_from_db()
        assert other_cashier.is_active is False

    def test_a_manager_cannot_deactivate_their_own_account(self, manager_client, manager):
        response = manager_client.patch(
            f"{USERS_URL}{manager.id}/", {"is_active": False}, format="json"
        )

        assert response.status_code == 400
        manager.refresh_from_db()
        assert manager.is_active is True

    def test_staff_are_deactivated_not_deleted(self, manager_client, other_cashier):
        """A staff account authors sales and adjustments; history needs its author."""
        response = manager_client.delete(f"{USERS_URL}{other_cashier.id}/")

        assert response.status_code == 405
        assert User.objects.filter(pk=other_cashier.pk).exists()

    def test_a_platform_account_cannot_be_reached(self, manager_client, platform_admin):
        response = manager_client.patch(
            f"{USERS_URL}{platform_admin.id}/", {"first_name": "Hacked"}, format="json"
        )

        assert response.status_code == 404

    def test_another_organizations_manager_cannot_reach_a_platform_account(
        self, rival_client, platform_admin
    ):
        response = rival_client.patch(
            f"{USERS_URL}{platform_admin.id}/", {"first_name": "Hacked"}, format="json"
        )

        assert response.status_code == 404

    def test_a_superuser_can_manage_platform_accounts(self, platform_client, platform_admin):
        """The guard is one-directional: it keeps tenant staff out, not operators."""
        response = platform_client.patch(
            f"{USERS_URL}{platform_admin.id}/", {"first_name": "Root"}, format="json"
        )

        assert response.status_code == 200, response.data
        platform_admin.refresh_from_db()
        assert platform_admin.first_name == "Root"


@pytest.mark.django_db
class TestRoleAssignment:
    def test_set_roles_replaces_the_existing_grants(self, manager_client, cashier):
        assert cashier.role_names() == ["CASHIER"]

        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/",
            {"roles": [{"role": "SUPERVISOR"}]},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["roles"] == ["SUPERVISOR"]
        assert UserRole.objects.filter(user=cashier).count() == 1

    def test_several_roles_can_be_held_at_once(self, manager_client, cashier):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/",
            {"roles": [{"role": "CASHIER"}, {"role": "SUPERVISOR"}]},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["roles"] == ["CASHIER", "SUPERVISOR"]

    def test_an_unknown_role_is_rejected(self, manager_client, cashier):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/",
            {"roles": [{"role": "SUPREME_LEADER"}]},
            format="json",
        )

        assert response.status_code == 400
        assert cashier.role_names() == ["CASHIER"]

    def test_a_role_can_be_granted_at_one_branch_only(self, manager_client, cashier, branch):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/",
            {"roles": [{"role": "SUPERVISOR", "branch": str(branch.id)}]},
            format="json",
        )

        assert response.status_code == 200, response.data
        grant = UserRole.objects.get(user=cashier)
        assert grant.branch_id == branch.id

    def test_a_branch_scoped_grant_does_not_apply_elsewhere(
        self, manager_client, cashier, branch, other_branch
    ):
        manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/",
            {"roles": [{"role": "SUPERVISOR", "branch": str(branch.id)}]},
            format="json",
        )

        assert user_has_permission(cashier, "sales.refund", branch_id=branch.id)
        assert not user_has_permission(cashier, "sales.refund", branch_id=other_branch.id)

    def test_a_grant_at_another_organizations_branch_is_rejected(
        self, manager_client, cashier, foreign_branch
    ):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/",
            {"roles": [{"role": "SUPERVISOR", "branch": str(foreign_branch.id)}]},
            format="json",
        )

        assert response.status_code == 400
        assert UserRole.objects.filter(user=cashier, branch=foreign_branch).count() == 0

    def test_the_same_role_cannot_be_listed_twice(self, manager_client, cashier):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/",
            {"roles": [{"role": "CASHIER"}, {"role": "CASHIER"}]},
            format="json",
        )

        assert response.status_code == 400

    def test_a_manager_cannot_widen_their_own_access(self, manager_client, manager):
        response = manager_client.post(
            f"{USERS_URL}{manager.id}/set-roles/",
            {"roles": [{"role": "ADMIN"}]},
            format="json",
        )

        assert response.status_code == 403
        assert manager.role_names() == ["MANAGER"]

    def test_grants_cannot_be_proposed_for_another_organizations_user(
        self, manager_client, rival_user
    ):
        response = manager_client.post(
            f"{USERS_URL}{rival_user.id}/set-roles/",
            {"roles": [{"role": "CASHIER"}]},
            format="json",
        )

        assert response.status_code == 404

    def test_clearing_the_roles_revokes_everything(self, manager_client, cashier):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-roles/", {"roles": []}, format="json"
        )

        assert response.status_code == 200, response.data
        assert response.data["roles"] == []
        assert not user_has_permission(cashier, "sales.create")


@pytest.mark.django_db
class TestBranchAccessAssignment:
    def test_assigning_branches_narrows_what_a_user_may_reach(
        self, manager_client, other_cashier, branch
    ):
        response = manager_client.post(
            f"{USERS_URL}{other_cashier.id}/set-branch-access/",
            {"branches": [{"branch": str(branch.id)}]},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["branch_ids"] == [str(branch.id)]

    def test_an_empty_list_makes_a_user_organization_wide(self, manager_client, cashier):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-branch-access/", {"branches": []}, format="json"
        )

        assert response.status_code == 200, response.data
        assert response.data["branch_ids"] == []
        assert UserBranchAccess.objects.filter(user=cashier).count() == 0

    def test_an_assignment_replaces_the_previous_one(
        self, manager_client, other_cashier, branch, other_branch
    ):
        url = f"{USERS_URL}{other_cashier.id}/set-branch-access/"

        manager_client.post(
            url, {"branches": [{"branch": str(branch.id)}, {"branch": str(other_branch.id)}]},
            format="json",
        )
        response = manager_client.post(
            url, {"branches": [{"branch": str(other_branch.id)}]}, format="json"
        )

        assert response.status_code == 200, response.data
        assert response.data["branch_ids"] == [str(other_branch.id)]

    def test_only_one_default_branch_is_allowed(
        self, manager_client, other_cashier, branch, other_branch
    ):
        response = manager_client.post(
            f"{USERS_URL}{other_cashier.id}/set-branch-access/",
            {
                "branches": [
                    {"branch": str(branch.id), "is_default": True},
                    {"branch": str(other_branch.id), "is_default": True},
                ]
            },
            format="json",
        )

        assert response.status_code == 400

    def test_a_branch_from_another_organization_is_rejected(
        self, manager_client, other_cashier, foreign_branch
    ):
        response = manager_client.post(
            f"{USERS_URL}{other_cashier.id}/set-branch-access/",
            {"branches": [{"branch": str(foreign_branch.id)}]},
            format="json",
        )

        assert response.status_code == 400
        assert UserBranchAccess.objects.filter(user=other_cashier).count() == 0

    def test_the_default_branch_follows_the_assignment(
        self, manager_client, other_cashier, branch
    ):
        manager_client.post(
            f"{USERS_URL}{other_cashier.id}/set-branch-access/",
            {"branches": [{"branch": str(branch.id), "is_default": True}]},
            format="json",
        )

        other_cashier.refresh_from_db()
        assert other_cashier.default_branch_id == branch.id

    def test_a_manager_cannot_change_their_own_postings(self, manager_client, manager):
        response = manager_client.post(
            f"{USERS_URL}{manager.id}/set-branch-access/", {"branches": []}, format="json"
        )

        assert response.status_code == 403


@pytest.mark.django_db
class TestPasswordReset:
    def test_a_manager_resets_a_cashiers_password(self, manager_client, cashier, login):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-password/",
            {"password": "brand-new-password-1"},
            format="json",
        )

        assert response.status_code == 200, response.data
        cashier.refresh_from_db()
        assert cashier.check_password("brand-new-password-1")

        assert login(cashier.username, "brand-new-password-1").status_code == 200

    def test_a_weak_password_is_rejected(self, manager_client, cashier):
        response = manager_client.post(
            f"{USERS_URL}{cashier.id}/set-password/", {"password": "123"}, format="json"
        )

        assert response.status_code == 400

    def test_the_old_password_stops_working(self, manager_client, cashier, login):
        manager_client.post(
            f"{USERS_URL}{cashier.id}/set-password/",
            {"password": "brand-new-password-1"},
            format="json",
        )

        assert login(cashier.username, "test-password-1").status_code == 401

    def test_a_cashier_cannot_reset_anybodys_password(self, authenticated_client, other_cashier):
        response = authenticated_client.post(
            f"{USERS_URL}{other_cashier.id}/set-password/",
            {"password": "brand-new-password-1"},
            format="json",
        )

        assert response.status_code == 403
        other_cashier.refresh_from_db()
        assert other_cashier.check_password("test-password-1")

    def test_a_platform_account_password_cannot_be_reset_here(
        self, manager_client, platform_admin
    ):
        response = manager_client.post(
            f"{USERS_URL}{platform_admin.id}/set-password/",
            {"password": "brand-new-password-1"},
            format="json",
        )

        assert response.status_code == 404


@pytest.mark.django_db
class TestManagerRoleScope:
    """The seeded MANAGER role is what these endpoints are written against."""

    def test_the_manager_role_carries_users_manage(self, db):
        role = Role.objects.get(name="MANAGER", organization__isnull=True)

        assert role.permissions.filter(code="users.manage").exists()

    def test_the_cashier_role_does_not(self, db):
        role = Role.objects.get(name="CASHIER", organization__isnull=True)

        assert not role.permissions.filter(code="users.manage").exists()
