from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.db import transaction
from rest_framework import serializers

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
    """Resolve one sale line's money from the catalogue.

    This is the single place a line's monetary truth is produced. The client
    supplies only the product and the quantity; the price comes from the
    product, the cost is captured for historical margin, and the tax comes from
    the product's tax band:

    - inclusive price: the customer pays ``price * quantity`` exactly, and the
      tax is carved back out of it;
    - exclusive price: the tax is added on top;
    - no tax band: tax is zero.

    Every value is quantized per line, so the sale total is the exact sum of
    its lines with no aggregate rounding drift.
    """
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
    # Nested serializers inherit the request context, so this check runs for each
    # line: a cashier must not be able to sell another organization's product.
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
        # Every monetary field is computed by the server from the product and
        # its tax configuration (``compute_line_money``). A client-sent value
        # for any of them is ignored rather than stored.
        read_only_fields = (
            "unit_price",
            "unit_cost",
            "subtotal",
            "tax_amount",
            "tax_rate_name",
            "tax_rate_percent",
        )

    def get_line_total(self, obj) -> Decimal:
        """What the customer pays for the line: net plus tax."""
        return obj.subtotal + obj.tax_amount


class SaleSerializer(OrganizationScopedSerializerMixin, serializers.ModelSerializer):
    organization_bound_fields = ("customer",)

    items = SaleItemSerializer(many=True)
    # Read-only and nested: the payment rows are the source of truth for how a
    # sale was settled, and become the record split payments read in phase 6.
    payments = PaymentSerializer(many=True, read_only=True)
    cashier_name = serializers.ReadOnlyField(source="cashier.username")
    customer_name = serializers.ReadOnlyField(source="customer.name")

    class Meta:
        model = Sale
        fields = (
            "id",
            "sale_number",
            "cashier",
            "cashier_name",
            "customer",
            "customer_name",
            "total_amount",
            "tax_amount",
            "discount_amount",
            "payment_method",
            "payments",
            "items",
            "created_at",
        )
        # The totals are computed from the items; the discount stays zero until
        # phase 6 decides how line-level discounts are priced. Line-level
        # discounts bolted onto the sale header cannot be explained per line.
        read_only_fields = ("total_amount", "tax_amount", "discount_amount")

    def validate_payment_method(self, value):
        """Only cash can be completed atomically with sale creation.

        M-Pesa is a two-step provider flow: the sale must exist before an STK
        request can reference it, and only the verified callback may complete
        the payment. Treating an MPESA sale as cash here would create a false
        completed payment and prevent the payment API from initiating the real
        collection.
        """
        if value != Sale.PaymentMethod.CASH:
            raise serializers.ValidationError(
                "M-Pesa payments must be initiated through the payments endpoint "
                "after the sale is created."
            )
        return value

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("A sale must contain at least one item.")
        for item in value:
            if item["quantity"] < 1:
                # A non-positive quantity would produce a negative-or-zero
                # total and *increase* stock — the opposite of a sale.
                raise serializers.ValidationError(
                    {"quantity": "Quantity must be at least 1."}
                )
        return value

    def _check_client_total_hint(self, computed_total: Decimal) -> None:
        """Treat a client-sent total as a mismatch hint, never as truth.

        A differing total is usually a buggy or desynchronised client, so it is
        rejected with the computed value in the message. A garbage value is
        rejected too: DRF no longer validates this field for us once it is
        read-only, so it is parsed here.
        """
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
                        f"of {computed_total}. Totals are calculated from the "
                        f"line items."
                    )
                }
            )

    @transaction.atomic
    def create(self, validated_data):
        """Persist a sale and its stock effects as one unit of work.

        Any failure rolls the whole thing back, so a sale can never exist
        without its stock deduction, or vice versa. Money is computed before
        anything is written, so a rejected total leaves no rows behind.
        """
        items_data = validated_data.pop("items")

        lines = [compute_line_money(item["product"], item["quantity"]) for item in items_data]
        subtotal = sum(line["subtotal"] for line in lines)
        tax_total = sum(line["tax_amount"] for line in lines)
        computed_total = subtotal + tax_total

        self._check_client_total_hint(computed_total)

        sale = Sale.objects.create(
            **validated_data,
            total_amount=computed_total,
            tax_amount=tax_total,
        )

        # The money received, recorded in the same transaction as the sale it
        # pays for. This is the one place sales reaches into the payments
        # domain: ``payments`` already points back at ``Sale`` for its foreign
        # key, so the edge exists in both directions until phase 6 rebuilds
        # ``Sale`` and moves payment creation into the new sales engine.
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

        # ``quantity`` is supplied per item; the line dict carries it only so
        # ``compute_line_money`` stays a pure, individually testable function.
        for line in lines:
            line.pop("quantity")

        for item_data, line in zip(items_data, lines, strict=True):
            # Lock the row: two cashiers must not oversell the last unit.
            product = Product.objects.select_for_update().get(pk=item_data["product"].pk)
            quantity = item_data["quantity"]

            if product.stock_level < quantity:
                raise serializers.ValidationError(
                    f"Insufficient stock for {product.name}. Available: {product.stock_level}."
                )

            SaleItem.objects.create(sale=sale, **item_data, **line)

            product.stock_level -= quantity
            product.save(update_fields=["stock_level", "updated_at"])

            StockAdjustment.objects.create(
                product=product,
                user=sale.cashier,
                quantity=-quantity,
                type=StockAdjustment.AdjustmentType.ADJUST,
                notes=f"Sale {sale.sale_number}",
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
