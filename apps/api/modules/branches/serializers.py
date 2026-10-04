from rest_framework import serializers

from .models import Branch


class BranchSerializer(serializers.ModelSerializer):
    organization_name = serializers.ReadOnlyField(source="organization.name")

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
