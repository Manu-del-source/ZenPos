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
    class Meta:
        model = Role
        fields = ("id", "name", "description", "is_system", "organization")
        read_only_fields = ("id", "is_system", "organization")

    def to_representation(self, instance):
        return RoleSerializer(instance, context=self.context).to_representation(instance)


class SetRolePermissionsSerializer(serializers.Serializer):
    permission_codes = serializers.ListField(child=serializers.CharField(), allow_empty=True)

    def validate_permission_codes(self, codes):
        known = set(Permission.objects.filter(code__in=codes).values_list("code", flat=True))
        unknown = sorted(set(codes) - known)
        if unknown:
            raise serializers.ValidationError(f"Unknown permission code(s): {', '.join(unknown)}.")
        return codes


class UserSerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()
    branch_ids = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "organization", "default_branch", "roles", "branch_ids",
            "permissions", "is_active", "is_superuser",
        )
        read_only_fields = fields

    def get_roles(self, obj):
        return obj.role_names()

    def get_branch_ids(self, obj):
        return [access.branch_id for access in obj.branch_access.all()]

    def get_permissions(self, obj):
        return sorted(permission_codes_for(obj))


class UserWriteSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    organization_bound_fields = ("default_branch",)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "is_active", "default_branch", "password",
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
        return UserSerializer(instance, context=self.context).to_representation(instance)

    def create(self, validated_data):
        password = validated_data.pop("password")
        with transaction.atomic():
            user = User.objects.create_user(password=password, **validated_data)
            record_audit(
                action="user.created", entity_type="user", entity_id=user.pk,
                actor=self.context["request"].user, request=self.context.get("request"),
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
                user.set_password(password)
                user.save(update_fields=["password", "updated_at"])
                record_audit(
                    action="user.password_reset", entity_type="user",
                    entity_id=user.pk, actor=request.user if request else None,
                    request=request,
                )
            record_audit(
                action="user.updated", entity_type="user", entity_id=user.pk,
                actor=request.user if request else None, request=request,
                before=before, after=snapshot(user, SAFE_USER_FIELDS),
            )
        return user


class RoleGrantSerializer(serializers.Serializer):
    role = serializers.CharField()
    branch = serializers.UUIDField(required=False, allow_null=True, default=None)


class RoleAssignmentSerializer(serializers.Serializer):
    roles = RoleGrantSerializer(many=True)

    def validate_roles(self, entries):
        caller = self.context["request"].user
        assignable = {role.name: role for role in Role.objects.visible_to(caller)}
        resolved, seen = [], set()
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
                raise serializers.ValidationError(f"'{name}' is listed twice for the same scope.")
            seen.add(key)
            resolved.append({"role": role, "branch_id": branch_id})
        return resolved


class BranchAccessEntrySerializer(serializers.Serializer):
    branch = serializers.UUIDField()
    is_default = serializers.BooleanField(required=False, default=False)


class BranchAccessAssignmentSerializer(serializers.Serializer):
    branches = BranchAccessEntrySerializer(many=True)

    def validate_branches(self, entries):
        caller = self.context["request"].user
        organization_id = caller.organization_id
        resolved, seen, defaults = [], set(), 0
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
    actor_name = serializers.ReadOnlyField(source="actor.username")
    branch_name = serializers.ReadOnlyField(source="branch.name")

    class Meta:
        model = AuditLog
        fields = (
            "id", "created_at", "action", "entity_type", "entity_id",
            "actor", "actor_name", "branch", "branch_name", "before",
            "after", "ip_address", "attempted_username",
        )
        read_only_fields = fields


class AuditedTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        record_audit(
            action="auth.login", entity_type="user", entity_id=self.user.pk,
            actor=self.user, request=self.context.get("request"),
        )
        return data
