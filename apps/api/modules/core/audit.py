"""The single writer of the audit log (ADR-0013).

The helper lives in ``core`` rather than ``accounts`` because every module
records events, and the import-direction rule says a module may only import
from modules above it — accounts sits below organizations and branches, which
would make their events unwritable from ``accounts``.

Every audit row is written through ``record_audit``, always inside the
database transaction that performs the change it describes. There is no
post-commit hook and no background queue: both can lose the row exactly when
the change it describes is contested, which is when the log matters most.

``price_history`` already records selling-price changes and is not duplicated
into this log; the boundary is recorded in ``record_audit``'s docstring.
"""

from .models import AuditLog

# Field names that are context, not state: they describe the row itself, so
# they never belong in a before/after snapshot.
NON_STATE_FIELDS = frozenset({"id", "created_at", "updated_at"})


def snapshot(instance, fields=None) -> dict | None:
    """Build a shallow, JSON-safe snapshot of an instance.

    Only concrete column values are taken. Related objects are not followed —
    a deep diff is a deliberate non-goal (ADR-0013) — and anything that does
    not survive JSON round-tripping is coerced to a string so one odd field
    can never stop an audit row from being written.

    Never point this at a user model without an explicit field list: the
    password hash is a concrete column and must not be copied into an
    auditable store.
    """
    if instance is None:
        return None

    field_names = (
        fields
        if fields is not None
        else [f.name for f in instance._meta.concrete_fields if f.name not in NON_STATE_FIELDS]
    )

    data = {}
    for name in field_names:
        value = getattr(instance, name, None)
        if value is None or isinstance(value, (str, int, float, bool)):
            data[name] = value
        else:
            data[name] = str(value)
    return data


def client_ip(request) -> str | None:
    """The client address for the audit row.

    Reads ``REMOTE_ADDR`` only. Proxy-supplied headers are not trusted: they
    are set by the caller and would let a forged request attribute its own
    audit row to someone else's address.
    """
    if request is None:
        return None
    return request.META.get("REMOTE_ADDR") or None


def record_audit(
    *,
    action: str,
    entity_type: str,
    entity_id=None,
    actor=None,
    request=None,
    branch=None,
    before: dict | None = None,
    after: dict | None = None,
    attempted_username: str = "",
) -> AuditLog:
    """Write one audit row. Call it inside the transaction of the change.

    ``price_history`` records selling-price changes already; those are not
    duplicated here. Password changes record *that* they happened, never the
    secret or its hash.

    Returns the row. It is deliberately not wrapped in try/except: if writing
    the audit row fails, the change it describes must roll back with it — a
    state change with no audit row is the failure mode this log exists to
    prevent.
    """
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else "",
        branch=branch,
        before=before,
        after=after,
        ip_address=client_ip(request),
        attempted_username=attempted_username or "",
    )
