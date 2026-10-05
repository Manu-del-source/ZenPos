from rest_framework import serializers

from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True, format="hex_verbose")
    organization = serializers.UUIDField(read_only=True, format="hex_verbose")
    organization_name = serializers.ReadOnlyField(source="organization.name")

    def validate_code(self, value):
        request = self.context.get("request")
        organization_id = getattr(getattr(request, "user", None), "organization_id", None)
        queryset = Branch.objects.filter(organization_id=organization_id, code=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "A branch with this code already exists in your organization."
            )
        return value

    class Meta:
        model = Branch
        fields = (
            "id",
            "organization",
            "organization_name",
            "name",
            "code",
            "address",
            "phone",
            "is_active",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "organization", "created_at", "updated_at")
