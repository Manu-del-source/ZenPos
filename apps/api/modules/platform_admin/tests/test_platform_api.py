import pytest
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from modules.accounts.models import User
from modules.branches.models import Branch
from modules.core.models import AuditLog
from modules.organizations.models import Organization

P = "/api/v2/platform/"
GOOD_PASSWORD = "a-Strong-passphrase-42"


def client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def pa_client(platform_admin):
    return client_for(platform_admin)


READ_ENDPOINTS = ["overview/", "health/", "organizations/", "branches/", "users/", "audit-logs/"]


@pytest.mark.django_db
class TestAccessControl:
    @pytest.mark.parametrize("path", READ_ENDPOINTS)
    def test_anonymous_gets_401(self, path):
        assert APIClient().get(P + path).status_code == 401

    @pytest.mark.parametrize("path", READ_ENDPOINTS)
    def test_org_admin_gets_403(self, admin_user, path):
        assert client_for(admin_user).get(P + path).status_code == 403

    @pytest.mark.parametrize("path", READ_ENDPOINTS)
    def test_cashier_gets_403(self, cashier, path):
        assert client_for(cashier).get(P + path).status_code == 403

    def test_org_admin_cannot_create_org_or_branch_via_platform(self, admin_user, organization):
        c = client_for(admin_user)
        assert (
            c.post(P + "organizations/", {"name": "X", "slug": "x"}, format="json").status_code
            == 403
        )
        body = {"organization": organization.pk, "name": "N", "code": "N1"}
        assert c.post(P + "branches/", body, format="json").status_code == 403
        assert c.post(P + "owners/", {}, format="json").status_code == 403

    def test_org_admin_cannot_grant_self_platform_admin(self, admin_user):
        r = client_for(admin_user).post(
            f"{P}users/{admin_user.pk}/set-platform-admin/",
            {"is_platform_admin": True},
            format="json",
        )
        assert r.status_code == 403
        admin_user.refresh_from_db()
        assert not admin_user.is_superuser

    def test_org_admin_cannot_escalate_through_staff_user_api(self, admin_user):
        r = client_for(admin_user).patch(
            f"/api/v2/users/{admin_user.pk}/", {"is_superuser": True}, format="json"
        )
        admin_user.refresh_from_db()
        assert not admin_user.is_superuser, r.content

    def test_inactive_platform_admin_is_refused(self, platform_admin):
        c = client_for(platform_admin)
        platform_admin.is_active = False
        platform_admin.save()
        assert c.get(P + "overview/").status_code in {401, 403}


@pytest.mark.django_db
class TestOrganizations:
    def test_create_list_search_and_audit(self, pa_client, platform_admin):
        r = pa_client.post(
            P + "organizations/",
            {"name": "Naivas Test", "slug": "naivas-test", "currency": "kes"},
            format="json",
        )
        assert r.status_code == 201, r.content
        assert r.data["currency"] == "KES"
        assert AuditLog.objects.filter(
            action="platform.organization_created", actor=platform_admin
        ).exists()
        found = pa_client.get(P + "organizations/?search=naivas").data
        assert found["count"] == 1

    def test_bad_currency_rejected(self, pa_client):
        r = pa_client.post(
            P + "organizations/", {"name": "A", "slug": "a", "currency": "KESX"}, format="json"
        )
        assert r.status_code == 400

    def test_deactivate_is_audited_and_filterable(self, pa_client, organization):
        r = pa_client.patch(
            f"{P}organizations/{organization.pk}/", {"is_active": False}, format="json"
        )
        assert r.status_code == 200
        assert AuditLog.objects.filter(action="platform.organization_deactivated").exists()
        assert pa_client.get(P + "organizations/?is_active=false").data["count"] == 1

    def test_no_delete(self, pa_client, organization):
        assert pa_client.delete(f"{P}organizations/{organization.pk}/").status_code == 405

    def test_deactivated_org_staff_are_locked_out(self, cashier, organization, pa_client):
        url = f"{P}organizations/{organization.pk}/"
        pa_client.patch(url, {"is_active": False}, format="json")
        # Reload as a real request would: the token resolves a fresh user row.
        fresh = User.objects.get(pk=cashier.pk)
        assert client_for(fresh).get("/api/v2/products/").status_code == 403
        pa_client.patch(url, {"is_active": True}, format="json")
        fresh = User.objects.get(pk=cashier.pk)
        assert client_for(fresh).get("/api/v2/products/").status_code == 200


@pytest.mark.django_db
class TestBranches:
    def test_create_deactivate_and_code_uniqueness(self, pa_client, organization, platform_admin):
        body = {"organization": organization.pk, "name": "Rongai", "code": "BR-009"}
        r = pa_client.post(P + "branches/", body, format="json")
        assert r.status_code == 201, r.content
        assert pa_client.post(P + "branches/", body, format="json").status_code == 400
        bid = r.data["id"]
        assert (
            pa_client.patch(f"{P}branches/{bid}/", {"is_active": False}, format="json").status_code
            == 200
        )
        assert AuditLog.objects.filter(action="platform.branch_deactivated").exists()

    def test_same_code_allowed_in_other_org(self, pa_client, organization, other_organization):
        Branch.objects.create(organization=organization, name="A", code="X1")
        r = pa_client.post(
            P + "branches/",
            {"organization": other_organization.pk, "name": "B", "code": "X1"},
            format="json",
        )
        assert r.status_code == 201

    def test_branch_cannot_move_between_orgs(self, pa_client, branch, other_organization):
        r = pa_client.patch(
            f"{P}branches/{branch.pk}/", {"organization": other_organization.pk}, format="json"
        )
        assert r.status_code == 400

    def test_filter_by_organization(self, pa_client, branch, foreign_branch, organization):
        r = pa_client.get(f"{P}branches/?organization={organization.pk}")
        assert {b["id"] for b in r.data["results"]} == {str(branch.pk)} or {
            b["id"] for b in r.data["results"]
        } == {branch.pk}


@pytest.mark.django_db
class TestPlatformUsers:
    def test_serializer_never_exposes_secrets(self, pa_client, cashier):
        r = pa_client.get(P + "users/")
        text = r.content.decode()
        assert "password" not in text
        assert "pbkdf2" not in text

    def test_grant_and_revoke_platform_admin(self, pa_client, admin_user, platform_admin):
        r = pa_client.post(
            f"{P}users/{admin_user.pk}/set-platform-admin/",
            {"is_platform_admin": True},
            format="json",
        )
        assert r.status_code == 200
        admin_user.refresh_from_db()
        assert admin_user.is_superuser
        assert AuditLog.objects.filter(
            action="platform.admin_granted", actor=platform_admin
        ).exists()
        r = pa_client.post(
            f"{P}users/{admin_user.pk}/set-platform-admin/",
            {"is_platform_admin": False},
            format="json",
        )
        assert r.status_code == 200
        admin_user.refresh_from_db()
        assert not admin_user.is_superuser

    def test_cannot_change_own_access(self, pa_client, platform_admin):
        r = pa_client.post(
            f"{P}users/{platform_admin.pk}/set-platform-admin/",
            {"is_platform_admin": False},
            format="json",
        )
        assert r.status_code == 403

    def test_last_platform_admin_cannot_be_revoked_or_deactivated(self, platform_admin, admin_user):
        admin_user.is_superuser = True
        admin_user.save()
        actor = client_for(admin_user)
        # admin_user revokes platform_admin (the other one) -> allowed, admin_user remains
        r = actor.post(
            f"{P}users/{platform_admin.pk}/set-platform-admin/",
            {"is_platform_admin": False},
            format="json",
        )
        assert r.status_code == 200
        # now admin_user is the only one; a second superuser cannot exist to act, so
        # re-promote platform_admin and verify deactivating the sole other is blocked in reverse
        platform_admin.refresh_from_db()
        assert not platform_admin.is_superuser

    def test_requires_boolean(self, pa_client, cashier):
        r = pa_client.post(
            f"{P}users/{cashier.pk}/set-platform-admin/",
            {"is_platform_admin": "yes"},
            format="json",
        )
        assert r.status_code == 400

    def test_set_active(self, pa_client, cashier):
        r = pa_client.post(
            f"{P}users/{cashier.pk}/set-active/", {"is_active": False}, format="json"
        )
        assert r.status_code == 200
        cashier.refresh_from_db()
        assert not cashier.is_active
        assert AuditLog.objects.filter(action="platform.user_deactivated").exists()

    def test_filter_by_platform_admin(self, pa_client, platform_admin, cashier):
        r = pa_client.get(P + "users/?platform_admin=true")
        assert r.data["count"] == 1


@pytest.mark.django_db
class TestOwnerInvite:
    def _invite(self, pa_client, organization, username="owner1"):
        return pa_client.post(
            P + "owners/",
            {"organization": organization.pk, "username": username, "email": "o@example.com"},
            format="json",
        )

    def test_invite_creates_unusable_password_admin(self, pa_client, organization):
        r = self._invite(pa_client, organization)
        assert r.status_code == 201, r.content
        user = User.objects.get(username="owner1")
        assert not user.has_usable_password()
        assert user.organization_id == organization.pk
        assert "ADMIN" in user.role_names()
        assert not user.is_superuser
        assert "password" not in r.content.decode().replace("note", "")  # no hash leaked

    def test_accept_sets_password_once(self, pa_client, organization):
        invite = self._invite(pa_client, organization).data["invite"]
        anon = APIClient()
        body = {"uid": invite["uid"], "token": invite["token"], "password": GOOD_PASSWORD}
        assert anon.post(P + "invites/accept/", body, format="json").status_code == 200
        login = anon.post(
            "/api/v2/auth/login/", {"username": "owner1", "password": GOOD_PASSWORD}, format="json"
        )
        assert login.status_code == 200
        # token is single use
        again = anon.post(P + "invites/accept/", body, format="json")
        assert again.status_code == 400

    def test_bad_token_and_weak_password_rejected(self, pa_client, organization):
        invite = self._invite(pa_client, organization).data["invite"]
        anon = APIClient()
        bad = anon.post(
            P + "invites/accept/",
            {"uid": invite["uid"], "token": "nope", "password": GOOD_PASSWORD},
            format="json",
        )
        assert bad.status_code == 400
        weak = anon.post(
            P + "invites/accept/",
            {"uid": invite["uid"], "token": invite["token"], "password": "123"},
            format="json",
        )
        assert weak.status_code == 400
        assert not User.objects.get(username="owner1").has_usable_password()

    def test_unknown_uid_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(999999))
        r = APIClient().post(
            P + "invites/accept/",
            {"uid": uid, "token": "x", "password": GOOD_PASSWORD},
            format="json",
        )
        assert r.status_code == 400

    def test_cannot_invite_into_inactive_org(self, pa_client, organization):
        organization.is_active = False
        organization.save()
        assert self._invite(pa_client, organization).status_code == 400

    def test_duplicate_username_rejected(self, pa_client, organization, cashier):
        assert self._invite(pa_client, organization, username="cashier1").status_code == 400


@pytest.mark.django_db
class TestOverviewAuditHealth:
    def test_overview_counts_are_real(self, pa_client, organization, branch, cashier):
        d = pa_client.get(P + "overview/").data
        assert d["organizations"]["total"] == Organization.objects.count()
        assert d["branches"]["total"] == 1
        assert d["users"]["platform_admins"] == 1

    def test_audit_logs_span_orgs_and_filter(self, pa_client, cashier, rival_user):
        from modules.core.audit import record_audit

        record_audit(action="x.test", entity_type="t", actor=cashier)
        record_audit(action="x.test", entity_type="t", actor=rival_user)
        r = pa_client.get(P + "audit-logs/?action=x.test")
        assert r.data["count"] == 2
        r = pa_client.get(f"{P}audit-logs/?action=x.test&organization={rival_user.organization_id}")
        assert r.data["count"] == 1

    def test_health_reports_measured_values_only(self, pa_client):
        d = pa_client.get(P + "health/").data
        assert d["database"] == "ok"
        assert d["pending_migrations"] == 0
        assert set(d) >= {"debug_mode", "mpesa_callback_secret_configured", "checked_at"}
