"""Transactional writer for the loyalty ledger."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from modules.core.audit import record_audit
from modules.customers.models import Customer

from .models import LoyaltyAccount, LoyaltyLedger, LoyaltyRule


def get_or_create_account(customer) -> LoyaltyAccount:
    account, _ = LoyaltyAccount.objects.get_or_create(
        customer=customer,
        defaults={"organization": customer.organization, "points_balance": 0},
    )
    return account


def rule_for(organization) -> LoyaltyRule | None:
    try:
        rule = LoyaltyRule.objects.get(organization=organization)
    except LoyaltyRule.DoesNotExist:
        return None
    return rule if rule.is_active else None


def points_for_sale(sale, rule: LoyaltyRule) -> int:
    if rule is None or not rule.is_active or rule.amount <= 0:
        return 0
    total = Decimal(sale.total_amount)
    return int(total / rule.amount) * int(rule.points)


@transaction.atomic
def apply_ledger(
    *,
    customer,
    points: int,
    action: str,
    organization=None,
    branch=None,
    reference_type: str = "",
    reference_id: str = "",
    actor=None,
    notes: str = "",
    request=None,
    allow_negative: bool = False,
) -> LoyaltyLedger | None:
    if points == 0:
        return None
    if customer is None:
        return None

    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    organization = organization or customer.organization
    account = get_or_create_account(customer)
    account = LoyaltyAccount.objects.select_for_update().get(pk=account.pk)

    new_balance = account.points_balance + points
    if new_balance < 0 and not allow_negative:
        raise ValidationError("Insufficient loyalty points.")

    ref_id = str(reference_id) if reference_id else ""
    if ref_id:
        existing = LoyaltyLedger.objects.filter(
            organization=organization,
            action=action,
            reference_type=reference_type or "",
            reference_id=ref_id,
        ).first()
        if existing is not None:
            return existing

    try:
        with transaction.atomic():
            entry = LoyaltyLedger.objects.create(
                organization=organization,
                account=account,
                customer=customer,
                branch=branch,
                points=points,
                action=action,
                reference_type=reference_type or "",
                reference_id=ref_id,
                actor=actor,
                notes=notes or "",
                balance_after=new_balance,
            )
    except IntegrityError:
        # Duplicate earn/redeem/reversal for the same reference.
        return (
            LoyaltyLedger.objects.filter(
                organization=organization,
                action=action,
                reference_type=reference_type or "",
                reference_id=ref_id,
            ).first()
        )

    account.points_balance = new_balance
    account.save(update_fields=["points_balance", "updated_at"])
    customer.loyalty_points = new_balance
    customer.save(update_fields=["loyalty_points"])

    record_audit(
        action=f"loyalty.{action.lower()}",
        entity_type="loyalty_ledger",
        entity_id=entry.pk,
        actor=actor,
        request=request,
        branch=branch,
        after={
            "customer": str(customer.pk),
            "points": points,
            "balance": new_balance,
            "reference_type": reference_type,
            "reference_id": str(reference_id) if reference_id else "",
        },
    )
    return entry


def award_sale_points(sale, actor=None, request=None) -> LoyaltyLedger | None:
    if sale.customer_id is None:
        return None
    rule = rule_for(sale.organization)
    points = points_for_sale(sale, rule) if rule else 0
    if points <= 0:
        return None
    return apply_ledger(
        customer=sale.customer,
        points=points,
        action=LoyaltyLedger.Action.EARN,
        organization=sale.organization,
        branch=sale.branch,
        reference_type="sale",
        reference_id=sale.pk,
        actor=actor or sale.cashier,
        notes=f"Sale {sale.sale_number}",
        request=request,
    )


def reverse_sale_points(sale, *, actor=None, request=None, reference_id=None) -> LoyaltyLedger | None:
    if sale.customer_id is None:
        return None
    earned = LoyaltyLedger.objects.filter(
        customer=sale.customer,
        action=LoyaltyLedger.Action.EARN,
        reference_type="sale",
        reference_id=str(sale.pk),
    ).first()
    if earned is None:
        return None
    return apply_ledger(
        customer=sale.customer,
        points=-earned.points,
        action=LoyaltyLedger.Action.REVERSAL,
        organization=sale.organization,
        branch=sale.branch,
        reference_type="sale",
        reference_id=sale.pk,
        actor=actor,
        notes=f"Reversal of {sale.sale_number}",
        request=request,
        allow_negative=True,
    )
