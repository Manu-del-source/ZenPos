"""Module-local operations on expenses.

The only state change this module allows is *append*: creating a genuine
expense or a reversal row for one. There is no edit and no delete anywhere in
the module, by design (ADR-0015).
"""

import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from modules.core.audit import record_audit, snapshot

from .models import Expense


def next_expense_number() -> str:
    """A human-readable, collision-proof expense number.

    Same shape as the sale numbers: a local-time stamp for sortable
    legibility plus a random tail, so two expenses recorded in the same
    second never collide.
    """
    return f"EXP-{timezone.localtime().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8].upper()}"


def reverse_expense(*, expense: Expense, actor, request=None) -> Expense:
    """Record a full-amount reversal for an expense.

    The original row is never touched; the correction is a new row that
    references it, written in the same transaction as the audit row. Partial
    corrections are out of scope on purpose: an expense is either right or
    reversed, and splitting a correction into parts multiplies the rows an
    accountant has to explain.
    """
    if expense.reversal_of is not None:
        raise ValidationError(
            "Reversals cannot be reversed; correct the original expense instead."
        )
    if expense.reversals.exists():
        raise ValidationError(f"Expense {expense.expense_number} has already been reversed.")

    with transaction.atomic():
        reversal = Expense.objects.create(
            organization=expense.organization,
            branch=expense.branch,
            category=expense.category,
            expense_number=next_expense_number(),
            date=expense.date,
            amount=expense.amount,
            reference=expense.reference,
            notes=f"Reversal of {expense.expense_number}",
            created_by=actor,
            reversal_of=expense,
        )
        record_audit(
            action="expense.reversed",
            entity_type="expense",
            entity_id=reversal.pk,
            actor=actor,
            request=request,
            branch=reversal.branch,
            before={"expense": expense.expense_number},
            after=snapshot(reversal),
        )
    return reversal
