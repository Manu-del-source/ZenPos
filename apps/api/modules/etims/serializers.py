from rest_framework import serializers

from .models import EtimsInvoice


class EtimsInvoiceSerializer(serializers.ModelSerializer):
    """Read-only surface: an invoice is written by the domain, never by a client."""

    sale_number = serializers.ReadOnlyField(source="sale.sale_number")
    branch_name = serializers.SerializerMethodField()

    def get_branch_name(self, obj):
        # Branch-less sales exist (the till did not name one); the receipt
        # prints an empty string for them, and so does the API.
        return obj.sale.branch.name if obj.sale.branch_id else ""

    class Meta:
        model = EtimsInvoice
        fields = (
            "id",
            "sale",
            "sale_number",
            "branch_name",
            "device",
            "status",
            "uin",
            "issued_at",
            "cancelled_at",
            "cancellation_reason",
            "line_items",
            "tax_breakdown",
            "subtotal",
            "tax_amount",
            "total_amount",
            "currency",
            "created_at",
        )
        read_only_fields = fields
