from django.contrib.auth import get_user_model
from rest_framework import serializers

from modules.branches.models import Branch
from modules.core.models import AuditLog
from modules.organizations.models import Organization

User = get_user_model()


class PlatformOrganizationSerializer(serializers.ModelSerializer):
    branch_count = serializers.IntegerField(read_only=True)
    user_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "name",
            "slug",
            "currency",
            "timezone",
            "is_active",
            "branch_count",
            "user_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_currency(self, value):
        value = value.upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Use a 3-letter ISO 4217 code, e.g. KES.")
        return value


class PlatformBranchSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Branch
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "code",
            "address",
            "phone",
            "timezone",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate(self, attrs):
        # ``organization`` is fixed at creation: moving a branch between tenants
        # would orphan its stock, sales and staff postings.
        if self.instance is not None and "organization" in attrs:
            if attrs["organization"].pk != self.instance.organization_id:
                raise serializers.ValidationError(
                    {"organization": "A branch cannot be moved to another organization."}
                )
        organization = attrs.get("organization") or getattr(self.instance, "organization", None)
        code = attrs.get("code", getattr(self.instance, "code", None))
        clash = Branch.objects.filter(organization=organization, code=code)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError({"code": "That branch code is already in use."})
        return attrs


class PlatformUserSerializer(serializers.ModelSerializer):
    """Deliberately explicit: no password hash, no tokens, no permissions dump."""

    organization_name = serializers.CharField(
        source="organization.name", read_only=True, default=None
    )
    roles = serializers.SerializerMethodField()
    is_platform_admin = serializers.BooleanField(source="is_superuser", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "organization",
            "organization_name",
            "is_active",
            "is_platform_admin",
            "roles",
            "last_login",
            "date_joined",
        ]
        read_only_fields = fields

    def get_roles(self, obj):
        return obj.role_names()


class OwnerInviteSerializer(serializers.Serializer):
    organization = serializers.PrimaryKeyRelatedField(queryset=Organization.objects.all())
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("That username is taken.")
        return value


class AcceptInviteSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class PlatformAuditLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source="actor.username", read_only=True, default=None)
    organization_name = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "created_at",
            "action",
            "entity_type",
            "entity_id",
            "actor_username",
            "attempted_username",
            "organization_name",
            "ip_address",
            "before",
            "after",
        ]
        read_only_fields = fields

    def get_organization_name(self, obj):
        actor = obj.actor
        if actor is not None and actor.organization_id:
            return actor.organization.name
        return None
