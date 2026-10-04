from rest_framework import serializers

from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    """A customer as the client sees them.

    ``organization`` is read-only: it is stamped from the caller, never accepted
    from the request body.

    ``loyalty_points`` is read-only as well. A balance that any client can patch
    is a balance nobody can explain, and the brief requires every points change
    to be a ledger entry. Phase 8 adds that ledger; until then the field is
    readable but not writable through this API.
    """

    class Meta:
        model = Customer
        fields = ("id", "organization", "name", "phone", "loyalty_points", "created_at")
        read_only_fields = ("id", "organization", "loyalty_points", "created_at")
