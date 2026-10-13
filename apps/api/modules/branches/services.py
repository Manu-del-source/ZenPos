"""Cash session operations: opening, cash movements, closing and review.

Every function here runs inside the caller's transaction (or opens its own)
and writes its audit row with the change, so a committed session state change
always has an audit row and a rolled-back one leaves none.

The money rule of this module: the drawer changes only through ``CashMovement``
rows. ``expected_cash`` is therefore always derivable — opening float plus the
signed sum of the session's movements — and the close compares that with the
physical count. The client may supply the physical count and a reason; it can
never supply the expected figure.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.core.audit import record_audit

from .models import CashMovement, CashSession, Till

MONEY_QUANTUM = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANTUM)


@transaction.atomic
def open_cash_session(*, till: Till, actor, opening_cash: Decimal, request=None) -> CashSession:
    """Open a cash session at ``till`` for ``actor``.

    Locks the till row so two simultaneous opens serialize: the second one sees
    the first session and is refused. The database's partial unique constraint
    on ``(till_id) WHERE status = OPEN`` is the backstop that makes this true
    even if the application check were bypassed.
    """
    till = Till.objects.select_for_update().get(pk=till.pk)

    if not till.is_active:
        raise ValidationError({"detail": "This till is deactivated."})

    if CashSession.objects.filter(till_id=till.pk, status=CashSession.Status.OPEN).exists():
        raise ValidationError(
            {"detail": "This till already has an open cash session."}
        )

    session = CashSession.objects.create(
        till=till,
        organization=till.organization,
        branch=till.branch,
        opened_by=actor,
        status=CashSession.Status.OPEN,
        opening_cash=_money(opening_cash),
    )
    record_audit(
        action="cash_session.opened",
        entity_type="cash_session",
        entity_id=session.pk,
        actor=actor,
        request=request,
        branch=session.branch,
        after={
            "till": str(till.pk),
            "opening_cash": str(session.opening_cash),
        },
    )
    return session


@transaction.atomic
def record_cash_movement(
    *,
    session: CashSession,
    movement_type: str,
    amount: Decimal,
    reason: str,
    actor,
    source: str = CashMovement.Source.MANUAL,
    reference: str = "",
    request=None,
) -> CashMovement:
    """Record one cash movement on an open session, inside the caller's transaction.

    ``amount`` must be positive — the direction is ``movement_type``. A closed
    session refuses movements: the drawer is sealed at close, and correcting a
    closed figure is a new, explicit movement on the next session's opening
    float, not an edit of history.
    """
    amount = _money(amount)
    if amount <= 0:
        raise ValidationError({"amount": "Amount must be greater than zero."})
    reason = reason.strip()
    if not reason:
        raise ValidationError({"reason": "A reason is required for cash movements."})

    session = CashSession.objects.select_for_update().get(pk=session.pk)
    if session.status != CashSession.Status.OPEN:
        raise ValidationError({"detail": "This session is closed; cash cannot move in or out."})

    movement = CashMovement.objects.create(
        session=session,
        organization=session.organization,
        branch=session.branch,
        movement_type=movement_type,
        source=source,
        amount=amount,
        reason=reason[:255],
        reference=reference[:64],
        created_by=actor,
    )
    record_audit(
        action="cash.movement.recorded",
        entity_type="cash_movement",
        entity_id=movement.pk,
        actor=actor,
        request=request,
        branch=session.branch,
        after={
            "session": str(session.pk),
            "movement_type": movement_type,
            "source": source,
            "amount": str(amount),
            "reason": movement.reason,
        },
    )
    return movement


def session_cash_totals(session: CashSession) -> dict:
    """Aggregate one session's drawer arithmetic from its movements alone.

    Returns unsigned Decimal parts plus the net, so a caller can present the
    breakdown or just the expected figure. No sales or payments table is read
    here: cash sales and cash refunds write movements when they happen, which
    is what keeps the drawer's story complete and this module's dependencies
    pointing the right way.
    """
    sums = {
        "cash_in_manual": Decimal("0.00"),
        "cash_in_sales": Decimal("0.00"),
        "cash_out_manual": Decimal("0.00"),
        "cash_out_refunds": Decimal("0.00"),
        "cash_drops": Decimal("0.00"),
    }
    for row in (
        session.movements.values("movement_type", "source")
        .annotate(total=Sum("amount"))
        .order_by()
    ):
        movement_type = row["movement_type"]
        source = row["source"]
        amount = _money(row["total"] or Decimal("0"))
        if movement_type == CashMovement.Type.CASH_IN:
            key = "cash_in_sales" if source == CashMovement.Source.SALE else "cash_in_manual"
            sums[key] += amount
        elif movement_type == CashMovement.Type.CASH_OUT:
            key = "cash_out_refunds" if source == CashMovement.Source.REFUND else "cash_out_manual"
            sums[key] += amount
        else:
            sums["cash_drops"] += amount

    net = (
        sums["cash_in_manual"]
        + sums["cash_in_sales"]
        - sums["cash_out_manual"]
        - sums["cash_out_refunds"]
        - sums["cash_drops"]
    )
    sums["net_movements"] = net
    sums["expected_cash"] = _money(session.opening_cash + net)
    return sums


@transaction.atomic
def close_cash_session(
    *,
    session: CashSession,
    actor,
    counted_cash: Decimal,
    notes: str = "",
    request=None,
) -> CashSession:
    """Close a session with a physical count; compute expected cash and the variance.

    Locks the session row, so a close and a same-instant sale or movement
    serialize: the sale either lands in the session before the aggregate runs
    or misses it entirely and belongs to the next shift. Closing is a
    one-way transition — a closed session cannot be reopened, and a repeated
    close is refused rather than applied twice.
    """
    session = CashSession.objects.select_for_update().get(pk=session.pk)
    if session.status == CashSession.Status.CLOSED:
        raise ValidationError({"detail": "This session is already closed."})

    totals = session_cash_totals(session)
    counted = _money(counted_cash)

    session.counted_cash = counted
    session.expected_cash = totals["expected_cash"]
    session.cash_variance = _money(counted - totals["expected_cash"])
    session.status = CashSession.Status.CLOSED
    session.close_notes = notes.strip()[:255]
    session.closed_at = timezone.now()
    session.closed_by = actor
    session.save()
    record_audit(
        action="cash_session.closed",
        entity_type="cash_session",
        entity_id=session.pk,
        actor=actor,
        request=request,
        branch=session.branch,
        before={"status": CashSession.Status.OPEN},
        after={
            "counted_cash": str(session.counted_cash),
            "expected_cash": str(session.expected_cash),
            "cash_variance": str(session.cash_variance),
            "movements": {k: str(v) for k, v in totals.items() if k != "expected_cash"},
        },
    )
    return session


@transaction.atomic
def review_cash_session(*, session: CashSession, actor, notes: str, request=None) -> CashSession:
    """Record a supervisor's review of a closed session's discrepancy.

    Review annotates; it never rewrites the count, the expected figure or the
    variance. A closed session without review yet is the normal case; reviewing
    an open session is refused because there is nothing closed to review.
    """
    session = CashSession.objects.select_for_update().get(pk=session.pk)
    if session.status != CashSession.Status.CLOSED:
        raise ValidationError({"detail": "Only a closed session can be reviewed."})

    notes = notes.strip()
    if not notes:
        raise ValidationError({"notes": "Review notes are required."})

    before = {
        "reviewed_by": str(session.reviewed_by_id) if session.reviewed_by_id else None,
        "review_notes": session.review_notes,
    }
    session.reviewed_by = actor
    session.reviewed_at = timezone.now()
    session.review_notes = notes[:255]
    session.save(update_fields=["reviewed_by", "reviewed_at", "review_notes", "updated_at"])
    record_audit(
        action="cash_session.reviewed",
        entity_type="cash_session",
        entity_id=session.pk,
        actor=actor,
        request=request,
        branch=session.branch,
        before=before,
        after={"review_notes": session.review_notes, "variance": str(session.cash_variance)},
    )
    return session


def reconciliation_for(session: CashSession) -> dict:
    """The full cash story of one session, for display and for reports."""
    totals = session_cash_totals(session)
    movement_counts = {
        key: session.movements.filter(movement_type=value).count()
        for key, value in (
            ("cash_in_count", CashMovement.Type.CASH_IN),
            ("cash_out_count", CashMovement.Type.CASH_OUT),
            ("cash_drop_count", CashMovement.Type.CASH_DROP),
        )
    }
    data = {
        "session": str(session.pk),
        "till": str(session.till_id),
        "status": session.status,
        "opened_by": session.opened_by.get_username(),
        "opening_cash": str(session.opening_cash),
        **{key: str(value) for key, value in totals.items() if key != "expected_cash"},
        "expected_cash": str(totals["expected_cash"]),
        "movement_counts": movement_counts,
        "created_at": session.created_at,
    }
    if session.status == CashSession.Status.CLOSED:
        data.update(
            counted_cash=str(session.counted_cash),
            cash_variance=str(session.cash_variance),
            close_notes=session.close_notes,
            closed_at=session.closed_at,
            closed_by=session.closed_by.get_username() if session.closed_by_id else None,
            reviewed_by=session.reviewed_by.get_username() if session.reviewed_by_id else None,
            reviewed_at=session.reviewed_at,
            review_notes=session.review_notes,
        )
    return data
