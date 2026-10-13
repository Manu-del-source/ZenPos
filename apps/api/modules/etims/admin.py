from django.contrib import admin

from .models import EtimsDevice, EtimsInvoice


@admin.register(EtimsDevice)
class EtimsDeviceAdmin(admin.ModelAdmin):
    """Registration data for KRA's ERS devices.

    ``api_key`` is a credential: it is set (via the field, which stays in
    the change form) but never listed, searched or shown, and KRA-assigned
    identifiers must be confirmed by a human before they are trusted.
    """

    list_display = ("name", "organization", "device_number", "is_active")
    list_filter = ("is_active", "organization")
    search_fields = ("name", "organization__name", "device_number")
    exclude = ("api_key",)


@admin.register(EtimsInvoice)
class EtimsInvoiceAdmin(admin.ModelAdmin):
    """Compliance documents: read in admin, written only by the domain.

    The Django admin is held to the same rule as the API (ADR-0013,
    ADR-0015, ADR-0019): a document is corrected by a cancellation, never
    edited or deleted.
    """

    can_delete = False
    list_display = (
        "sale",
        "status",
        "uin",
        "issued_at",
        "total_amount",
        "cancellation_reason",
    )
    list_filter = ("status",)
    search_fields = ("sale__sale_number", "uin", "cancellation_reason")

    def has_add_permission(self, request):
        # Even a backfill goes through the domain, which writes the row and
        # its audit together; an admin "add" would be a document with no
        # trail.
        return False

    def has_change_permission(self, request, obj=None):
        # The invoice row and its snapshots are written once, at issue, and
        # transitioned by the domain. Everything else is a rewrite.
        return False

    def has_delete_permission(self, request, obj=None):
        # A cancelled invoice is the correction. Deleting the document would
        # delete the explanation.
        return False
