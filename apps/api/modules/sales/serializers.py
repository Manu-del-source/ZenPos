import uuid
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from rest_framework import serializers

from modules.branches.models import Branch
from modules.catalog.models import Product
from modules.core.audit import record_audit
from modules.core.serializers import OrganizationScopedSerializerMixin
from modules.inventory.models import StockAdjustment
from modules.payments.serializers import PaymentSerializer
from modules.payments.services import complete_cash_payment

from .models import Sale, SaleItem

# Money is handled to the cent everywhere. ROUND_HALF_UP is what a cashier's
# till and every Kenyan tax invoice expect; Python's default (banker's
# rounding) would drift from both.
QUANTUM = Decimal("0.01")
TOTAL_TOLERANCE = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(QUANTUM, rounding=ROUND_HALF_UP)


def compute_line_money(product: Product, quantity: int) -> dict:
    """Resolve one sale line's money from the catalogue."""
    gross = _money(product.price * quantity)
    tax_rate = product.tax_rate

    if tax_rate is None:
        return {
            "unit_price": _money(product.price),
            "unit_cost": _money(product.cost_price),
            "quantity": quantity,
            "subtotal": gross,
            "tax_amount": Decimal("0.00"),
            "tax_rate_name": "",
            "tax_rate_percent": None,
        }

    rate = tax_rate.rate / Decimal("100")
    if tax_rate.is_inclusive:
        tax_amount = _money(gross * rate / (Decimal("1") + rate))
        subtotal = gross - tax_amount
    else:
        subtotal = gross
        tax_amount = _money(subtotal * rate)

    return {
        "unit_price": _money(product.price),
        "unit_cost": _money(product.cost_price),
        "quantity": quantity,
        "subtotal": subtotal,
        "tax_amount": tax_amount,
        "tax_rate_name": tax_rate.name,
        "tax_rate_percent": tax_rate.rate,
    }


class SaleItemSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    organization_bound_fields = ("product",)

    product_name = serializers.ReadOnlyField(source="product.name")
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = SaleItem
        fields = (
            "id",
            "product",
            "product_name",
            "quantity",
            "unit_price",
            "unit_cost",
            "subtotal",
            "tax_amount",
            "line_total",
            "tax_rate_name",
            "tax_rate_percent",
        )
        read_only_fields = (
            "unit_price",
            "unit_cost",
            "subtotal",
            "tax_amount",
            "tax_rate_name",
            "tax_rate_percent",
        )

    def get_line_total(self, obj) -> Decimal:
        return obj.subtotal + obj.tax_amount


class SaleSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    organization_bound_fields = ("customer",)

    items = SaleItemSerializer(many=True)
    payments = PaymentSerializer(many=True, read_only=True)
    cashier_name = serializers.ReadOnlyField(source="cashier.username")
    customer_name = serializers.ReadOnlyField(source="customer.name")
    branch_name = serializers.ReadOnlyField(source="branch.name")
    voided_by_name = serializers.ReadOnlyField(source="voided_by.username")
    client_reference = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        default="",
        help_text="Idempotency key: two requests with the same value produce one sale.",
    )
    branch = serializers.PrimaryKeyRelatedField(
        queryset=Branch.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = Sale
        fields = (
            "id",
            "sale_number",
            "client_reference",
            "cashier",
            "cashier_name",
            "organization",
            "branch",
            "branch_name",
            "customer",
            "customer_name",
            "total_amount",
            "tax_amount",
            "discount_amount",
            "payment_method",
            "status",
            "voided_at",
            "voided_by",
            "voided_by_name",
            "void_reason",
            "payments",
            "items",
            "created_at",
        )
        read_only_fields = (
            "sale_number",
            "cashier",
            "organization",
            "total_amount",
            "tax_amount",
            "discount_amount",
            "status",
            "voided_at",
            "voided_by",
            "void_reason",
        )

    def validate_payment_method(self, value):
        if value not in {Sale.PaymentMethod.CASH, Sale.PaymentMethod.MPESA}:
            raise serializers.ValidationError(
                "Only CASH and MPESA are currently supported at the POS."
            )
        return value

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("A sale must contain at least one item.")
        for item in value:
            if item["quantity"] < 1:
                raise serializers.ValidationError(
                    {"quantity": "Quantity must be at least 1."}
                )
        return value

    def validate_branch(self, branch):
        """A branch the caller may actually sell from."""
        if branch is None:
            return None
        user = self.request_user
        if user is None or not getattr(user, "is_authenticated", False):
            return branch

        if getattr(user, "is_superuser", False):
            return branch

        organization_id = getattr(user, "organization_id", None)
        if branch.organization_id != organization_id:
            raise serializers.ValidationError(
                "That branch belongs to a different organization."
            )

        allowed = set(user.branch_access.values_list("branch_id", flat=True))
        if allowed and branch.pk not in allowed:
            raise serializers.ValidationError(
                "You are not posted to that branch, so you cannot sell from it."
            )
        return branch

    def _resolve_branch(self, cashier):
        """Where this sale happened.

        An explicit, permitted branch always wins. Otherwise the cashier's
        default branch, then the posting they flagged as default, then a single
        posting, then the organization's only branch. A head-office user in a
        multi-branch organization has to say which shop they are selling from
        rather than have real money attributed to a guess.
        """
        requested = self.validated_data.get("branch")
        if requested is not None:
            return requested

        user = self.request_user or cashier
        if user is None:
            return None

        if getattr(user, "default_branch", None) is not None:
            return user.default_branch

        postings = list(user.branch_access.select_related("branch").all())
        flagged = [posting.branch for posting in postings if posting.is_default]
        if flagged:
            return flagged[0]
        if len(postings) == 1:
            return postings[0].branch

        if not postings:
            from modules.branches.models import Branch

            organization_id = getattr(user, "organization_id", None)
            if organization_id is not None:
                branches = list(Branch.objects.filter(organization_id=organization_id)[:2])
                if len(branches) == 1:
                    return branches[0]
                if not branches:
                    # A business that never opened a branch record has nothing
                    # to attribute the sale to; the row stays unattributed
                    # rather than blocking the till.
                    return None

        raise serializers.ValidationError(
            {"branch": "Select the branch this sale belongs to."}
        )

    def _check_client_total_hint(self, computed_total: Decimal) -> None:
        client_total = self.initial_data.get("total_amount")
        if client_total is None:
            return
        try:
            hinted = Decimal(str(client_total))
        except InvalidOperation as exc:
            raise serializers.ValidationError(
                {"total_amount": "If sent, total_amount must be a number."}
            ) from exc
        if abs(hinted - computed_total) > TOTAL_TOLERANCE:
            raise serializers.ValidationError(
                {
                    "total_amount": (
                        f"Client total does not match the server-computed total "
                        f"of {computed_total}. Totals are calculated from the line items."
                    )
                }
            )

    @property
    def replayed(self) -> bool:
        """True when this request returned an existing sale instead of a new one."""
        return getattr(self, "_replayed", False)

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")

        lines = [
            compute_line_money(item["product"], item["quantity"])
            for item in items_data
        ]
        subtotal = sum(line["subtotal"] for line in lines)
        tax_total = sum(line["tax_amount"] for line in lines)
        computed_total = subtotal + tax_total

        self._check_client_total_hint(computed_total)

        # Sale numbers are generated by the server so every POS client,
        # including older deployed frontends, can create a sale safely.
        validated_data.pop("sale_number", None)
        sale_number = f"SALE-{timezone_now_stamp()}-{uuid.uuid4().hex[:8].upper()}"

        cashier = validated_data["cashier"]
        branch = self._resolve_branch(cashier)
        reference = validated_data.pop("client_reference", "")

        # Idempotency, decided by the client's reference rather than by
        # anything the client claims about the sale: a POS retry after a
        # dropped connection must not become a second sale with a second stock
        # movement. The unique constraint below is the authority; this lookup
        # only avoids the exception on the common path.
        if reference:
            existing = Sale.objects.filter(
                organization_id=cashier.organization_id, client_reference=reference
            ).first()
            if existing is not None:
                self._replayed = True
                return existing

        payload = {
            **validated_data,
            "organization_id": cashier.organization_id,
            "branch": branch,
        }

        try:
            with transaction.atomic():
                sale = Sale.objects.create(
                    **payload,
                    sale_number=sale_number,
                    client_reference=reference,
                    total_amount=computed_total,
                    tax_amount=tax_total,
                )
        except IntegrityError:
            # Two retries raced. The loser reads the winner's sale and returns
            # it: same money, same stock movement, answered once.
            if not reference:
                raise
            replay = Sale.objects.filter(
                organization_id=cashier.organization_id, client_reference=reference
            ).first()
            if replay is None:
                raise
            self._replayed = True
            return replay

        if sale.payment_method == Sale.PaymentMethod.CASH:
            payment = complete_cash_payment(
                sale=sale, amount=computed_total, received_by=sale.cashier
            )
            record_audit(
                action="payment.completed",
                entity_type="payment",
                entity_id=payment.pk,
                actor=sale.cashier,
                request=self.context.get("request"),
                after={
                    "sale": str(sale.pk),
                    "method": payment.method,
                    "amount": str(payment.amount),
                    "status": payment.status,
                },
            )

        for line in lines:
            line.pop("quantity")

        for item_data, line in zip(items_data, lines, strict=True):
            product = Product.objects.select_for_update().get(pk=item_data["product"].pk)
            quantity = item_data["quantity"]

            # Non-stocked products (services, fees, etc.) never participate in
            # inventory validation or stock movements.
            if product.track_inventory:
                if product.stock_level < quantity:
                    raise serializers.ValidationError(
                        f"Insufficient stock for {product.name}. Available: {product.stock_level}."
                    )

            SaleItem.objects.create(sale=sale, **item_data, **line)

            if product.track_inventory:
                # For M-Pesa this is a reservation: the stock is held while the
                # customer completes the STK prompt and is released automatically
                # if the provider reports failure. Cash sales are immediately
                # completed, so the same movement is the final deduction.
                product.stock_level -= quantity
                product.save(update_fields=["stock_level", "updated_at"])

                StockAdjustment.objects.create(
                    product=product,
                    user=sale.cashier,
                    quantity=-quantity,
                    type=StockAdjustment.AdjustmentType.ADJUST,
                    notes=(
                        f"Sale {sale.sale_number}"
                        + (
                            " - M-Pesa pending reservation"
                            if sale.payment_method == Sale.PaymentMethod.MPESA
                            else ""
                        )
                    ),
                )
                record_audit(
                    action="stock.adjusted",
                    entity_type="product",
                    entity_id=product.pk,
                    actor=sale.cashier,
                    request=self.context.get("request"),
                    after={"stock_level": product.stock_level},
                )

        record_audit(
            action="sale.created",
            entity_type="sale",
            entity_id=sale.pk,
            actor=sale.cashier,
            request=self.context.get("request"),
            after={
                "sale_number": sale.sale_number,
                "total_amount": str(sale.total_amount),
                "tax_amount": str(sale.tax_amount),
                "payment_method": sale.payment_method,
                "line_count": len(lines),
            },
        )

        return sale


def timezone_now_stamp():
    from django.utils import timezone
    return timezone.now().strftime("%Y%m%d%H%M%S")
