from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from modules.branches.models import Branch
from modules.core.audit import record_audit, snapshot
from modules.core.models import AuditLog
from modules.core.serializers import OrganizationScopedSerializerMixin

from .models import Permission, Role, User
from .permissions import permission_codes_for

# Columns safe to copy into an audit row. The password hash is deliberately
# absent: an audit store must never hold material that unlocks an account.
SAFE_USER_FIELDS = (
    "username",
    "email",
    "first_name",
    "last_name",
    "is_active",
    "default_branch",
    "organization",
)


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ("id", "code", "module", "description")
        read_only_fields = fields


class RoleSerializer(serializers.ModelSerializer):
    """A role and the permission codes it carries. Read-only."""

    permissions = PermissionSerializer(many=True, read_only=True)
    permission_codes = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = (
            "id",
            "name",
            "description",
            "is_system",
            "organization",
            "permissions",
            "permission_codes",
        )
        read_only_fields = fields

    def get_permission_codes(self, obj):
        return sorted(p.code for p in obj.permissions.all())


class RoleWriteSerializer(serializers.ModelSerializer):
    """Create or rename an organization-owned role.

    Permissions are not set here. Changing what a role can do is a privilege
    operation with its own endpoint (``POST /roles/{id}/set-permissions/``), so
    that a rename can never quietly re-scope authorization.
    """

    class Meta:
        model = Role
        fields = ("id", "name", "description", "is_system", "organization")
        read_only_fields = ("id", "is_system", "organization")

    def to_representation(self, instance):
        """Respond with the full read shape, so a client needs no second GET."""
        return RoleSerializer(instance, context=self.context).to_representation(instance)


class SetRolePermissionsSerializer(serializers.Serializer):
    """The complete permission set a role should carry. Omitted codes are revoked."""

    permission_codes = serializers.ListField(child=serializers.CharField(), allow_empty=True)

    def validate_permission_codes(self, codes):
        known = set(Permission.objects.filter(code__in=codes).values_list("code", flat=True))
        unknown = sorted(set(codes) - known)
        if unknown:
            # A typo in an authorization list is a security bug, not a cosmetic
            # one: reject it rather than silently dropping the grant.
            raise serializers.ValidationError(f"Unknown permission code(s): {', '.join(unknown)}.")
        return codes


class UserSerializer(serializers.ModelSerializer):
    """The authenticated user's own view of their account.

    Read-only throughout: profile and permission changes go through the
    management endpoints or the admin, never through the token holder editing
    their own roles. ``permissions`` is what the client is *shown* so it can hide
    what the user cannot do; the server re-checks every request regardless.
    """

    roles = serializers.SerializerMethodField()
    branch_ids = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "organization",
            "default_branch",
            "roles",
            "branch_ids",
            "permissions",
            "is_active",
        )
        read_only_fields = fields

    def get_roles(self, obj):
        return obj.role_names()

    def get_branch_ids(self, obj):
        return [access.branch_id for access in obj.branch_access.all()]

    def get_permissions(self, obj):
        return sorted(permission_codes_for(obj))


class UserWriteSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    """Create or edit a staff account.

    ``organization`` is never accepted from the client: the account is created in
    the caller's organization. ``is_superuser`` and ``is_staff`` are not settable
    here either — platform operators are created by hand, not through the API.
    """

    organization_bound_fields = ("default_branch",)

    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "default_branch",
            "password",
        )
        read_only_fields = ("id",)

    def validate_password(self, value):
        validate_password(value)
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance is None and not attrs.get("password"):
            raise serializers.ValidationError({"password": "Required when creating a user."})
        return attrs

    def to_representation(self, instance):
        """Respond with the full read shape, so a client needs no second GET."""
        return UserSerializer(instance, context=self.context).to_representation(instance)

    def create(self, validated_data):
        password = validated_data.pop("password")

        with transaction.atomic():
            user = User.objects.create_user(password=password, **validated_data)
            record_audit(
                action="user.created",
                entity_type="user",
                entity_id=user.pk,
                actor=self.context["request"].user,
                request=self.context.get("request"),
                after=snapshot(user, SAFE_USER_FIELDS),
            )
            return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        request = self.context.get("request")

        with transaction.atomic():
            before = snapshot(instance, SAFE_USER_FIELDS)
            user = super().update(instance, validated_data)

            if password:
                # set_password, not assignment: an unwritten password must stay
                # valid.
                user.set_password(password)
                user.save(update_fields=["password", "updated_at"])
                # Records *that* the password changed. Neither the secret nor
                # its hash is ever snapshotted.
                record_audit(
                    action="user.password_reset",
                    entity_type="user",
                    entity_id=user.pk,
                    actor=request.user if request else None,
                    request=request,
                )

            record_audit(
                action="user.updated",
                entity_type="user",
                entity_id=user.pk,
                actor=request.user if request else None,
                request=request,
                before=before,
                after=snapshot(user, SAFE_USER_FIELDS),
            )

        return user


class RoleGrantSerializer(serializers.Serializer):
    """One role grant: a role, and the branch it applies to.

    ``branch`` absent or null means the grant applies wherever the user can work.
    Naming a branch restricts the grant to that branch.
    """

    role = serializers.CharField()
    branch = serializers.UUIDField(required=False, allow_null=True, default=None)


class RoleAssignmentSerializer(serializers.Serializer):
    """The complete set of grants a user should hold.

    Replacement semantics, not append: a role omitted here is revoked. Role names
    rather than ids, because that is what an operator reads in the UI, and the
    set is validated against the roles the caller can actually assign.
    """

    roles = RoleGrantSerializer(many=True)

    def validate_roles(self, entries):
        caller = self.context["request"].user
        assignable = {role.name: role for role in Role.objects.visible_to(caller)}

        resolved = []
        seen = set()

        for entry in entries:
            name = entry["role"]
            role = assignable.get(name)
            if role is None:
                raise serializers.ValidationError(f"'{name}' is not a role you can assign.")

            branch_id = entry["branch"]
            if branch_id is not None:
                in_organization = Branch.objects.filter(
                    pk=branch_id, organization_id=caller.organization_id
                ).exists()
                if not in_organization:
                    raise serializers.ValidationError(
                        f"Branch {branch_id} is not in your organization."
                    )

            key = (role.pk, branch_id)
            if key in seen:
                raise serializers.ValidationError(
                    f"'{name}' is listed twice for the same scope."
                )
            seen.add(key)

            resolved.append({"role": role, "branch_id": branch_id})

        return resolved


class BranchAccessEntrySerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    is_default = serializers.BooleanField(required=False, default=False)


class BranchAccessAssignmentSerializer(serializers.Serializer):
    """The complete set of branches a user is posted to.

    Replacement semantics: a branch omitted here is removed from the user's
    postings. An empty list makes the user organization-wide, which is the state
    a head-office account is in.
    """

    branches = BranchAccessEntrySerializer(many=True)

    def validate_branches(self, entries):
        caller = self.context["request"].user
        organization_id = caller.organization_id

        resolved = []
        seen = set()
        defaults = 0

        for entry in entries:
            branch_id = entry["branch"]
            if branch_id in seen:
                raise serializers.ValidationError(f"Branch {branch_id} is listed twice.")
            seen.add(branch_id)

            if not Branch.objects.filter(
                pk=branch_id, organization_id=organization_id
            ).exists():
                raise serializers.ValidationError(
                    f"Branch {branch_id} is not in your organization."
                )

            if entry["is_default"]:
                defaults += 1

            resolved.append(entry)

        if defaults > 1:
            raise serializers.ValidationError("Only one branch may be the default.")

        return resolved


class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value):
        validate_password(value)
        return value


class AuditLogSerializer(serializers.ModelSerializer):
    """An audit row as the API serves it: read-only throughout, of course."""

    actor_name = serializers.ReadOnlyField(source="actor.username")
    branch_name = serializers.ReadOnlyField(source="branch.name")

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "created_at",
            "action",
            "entity_type",
            "entity_id",
            "actor",
            "actor_name",
            "branch",
            "branch_name",
            "before",
            "after",
            "ip_address",
            "attempted_username",
        )
        read_only_fields = fields


class AuditedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """The default pair serializer, plus an ``auth.login`` audit row.

    SimpleJWT never calls ``django.contrib.auth.login()``, so the
    ``user_logged_in`` signal does not fire on the API path — this override is
    what makes login rows exist for the endpoint every client actually uses.
    Failed attempts need no override: ``ModelBackend.authenticate`` sends the
    ``user_login_failed`` signal, which the receivers in ``signals.py`` write.
    """

    def validate(self, attrs):
        data = super().validate(attrs)
        record_audit(
            action="auth.login",
            entity_type="user",
            entity_id=self.user.pk,
            actor=self.user,
            request=self.context.get("request"),
        )
        return data
