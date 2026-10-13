from django.utils.text import slugify
from rest_framework import serializers

from .models import Organization


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = (
            "id",
            "name",
            "slug",
            "currency",
            "timezone",
            "is_active",
            "created_at",
            "updated_at",
        )
        # ``is_active`` is not tenant-writable: closing a tenant is a
        # platform action (``/platform/organizations/{id}/suspend/``), and a
        # tenant that could flip the switch itself could also find itself
        # locked out with no way back.
        read_only_fields = ("id", "slug", "is_active", "created_at", "updated_at")


class PlatformOrganizationOnboardSerializer(serializers.Serializer):
    """The shape of a tenant as the platform opens it.

    Flat on purpose: onboarding is a rare, careful act, and a nested payload
    buys nothing over a page of labelled fields.
    """

    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=80, required=False, allow_blank=True)
    currency = serializers.RegexField(r"^[A-Z]{3}$", default="KES")
    timezone = serializers.CharField(max_length=64, default="Africa/Nairobi")
    branch_name = serializers.CharField(max_length=255)
    branch_code = serializers.CharField(max_length=32)
    admin_username = serializers.CharField(max_length=150)
    admin_password = serializers.CharField(write_only=True, style={"input_type": "password"})
    admin_email = serializers.EmailField(required=False, allow_blank=True, default="")

    def validate(self, attrs):
        slug = attrs.get("slug") or slugify(attrs["name"])
        if not slug:
            raise serializers.ValidationError(
                {"slug": "The name does not slugify to anything; provide a slug."}
            )
        if Organization.objects.filter(slug=slug).exists():
            raise serializers.ValidationError(
                {"slug": "An organization with this slug already exists."}
            )
        attrs["slug"] = slug
        return attrs
