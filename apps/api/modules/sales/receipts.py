"""Receipt rendering (phase 5, workstream 4).

Receipts render recorded truth and nothing else: the totals the server
computed at sale time (workstream 1), the per-line tax snapshots, and the
payment rows (workstream 3). No client-supplied number can appear on a
receipt, because no client-supplied number was ever stored.

The tax breakdown is grouped **per tax rate** — name, rate, net, tax. That
grouping is what makes the eTIMS adapter (phase 8) a formatting concern
instead of a data problem: eTIMS wants tax per rate, and the lines already
carry the rate they were sold under, so a later price change on a product can
never rewrite what this receipt says.

Two renderings come from one context:

- an HTML reprint for the back office (``?paper=80mm|a4``), and
- a plain-text layout, 42 or 48 columns, that a POS terminal can pipe to a
  thermal printer today. ESC/POS byte commands (cut, drawer, codepage)
  arrive with the POS PWA in phase 6 — this is the text source.
"""

from decimal import Decimal

COLUMNS_80MM = 42
COLUMNS_80MM_WIDE = 48
COLUMNS_58MM = 32
DEFAULT_THERMAL_COLUMNS = COLUMNS_80MM

LINE = "-"


def build_receipt_context(sale) -> dict:
    """Everything a receipt says, read from persisted rows only."""
    items = list(sale.items.all())

    # Group tax per rate from the per-line snapshots. A dict keyed on
    # (name, percent) keeps groups in first-appearance order, which matches
    # the order the lines were rung up.
    tax_groups: dict[tuple[str, str], dict] = {}
    for item in items:
        percent = "" if item.tax_rate_percent is None else str(item.tax_rate_percent)
        key = (item.tax_rate_name, percent)
        group = tax_groups.setdefault(
            key,
            {
                "name": item.tax_rate_name or "No tax",
                "rate": item.tax_rate_percent,
                "net": Decimal("0.00"),
                "tax": Decimal("0.00"),
            },
        )
        group["net"] += item.subtotal
        group["tax"] += item.tax_amount

    organization = sale.organization or getattr(sale.cashier, "organization", None)

    return {
        "organization_name": organization.name if organization else "",
        "currency": organization.currency if organization else "KES",
        "branch_name": sale.branch.name if sale.branch_id else "",
        "sale_number": sale.sale_number,
        "created_at": sale.created_at,
        "cashier_name": sale.cashier.get_username(),
        "customer_name": sale.customer.name if sale.customer_id else "",
        "items": [
            {
                "name": item.product.name,
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "line_total": item.subtotal + item.tax_amount,
            }
            for item in items
        ],
        "tax_groups": list(tax_groups.values()),
        "payments": [
            {
                "method": payment.method,
                "status": payment.status,
                "amount": payment.amount,
                "provider_reference": payment.provider_reference,
            }
            for payment in sale.payments.all()
        ],
        "subtotal": sum((item.subtotal for item in items), Decimal("0.00")),
        "tax_amount": sale.tax_amount,
        "total_amount": sale.total_amount,
        "discount_amount": sale.discount_amount,
    }


def _money(amount: Decimal) -> str:
    return f"{amount:.2f}"


def render_thermal_receipt(context: dict, columns: int = DEFAULT_THERMAL_COLUMNS) -> str:
    """Render the receipt as fixed-width text for a thermal printer.

    Names go left, money goes right, and anything wider than its column is
    truncated rather than allowed to wrap — a misaligned receipt is a worse
    failure than a truncated name.
    """
    width = columns
    amount_width = 10
    label_width = width - amount_width

    def two_col(left: str, right: str) -> str:
        return f"{left[:label_width]:<{label_width}}{right[:amount_width]:>{amount_width}}"

    def centered(text: str) -> str:
        return text[:width].center(width).rstrip()

    lines: list[str] = [centered(context["organization_name"]), centered(context["sale_number"])]

    if context.get("branch_name"):
        lines.append(centered(context["branch_name"]))
    lines.append(context["created_at"].strftime("%Y-%m-%d %H:%M"))
    lines.append(f"Cashier: {context['cashier_name']}")
    if context["customer_name"]:
        lines.append(f"Customer: {context['customer_name']}")
    lines.append(LINE * width)

    for item in context["items"]:
        lines.append(item["name"][:width])
        quantity_line = f"  {item['quantity']} x {_money(item['unit_price'])}"
        lines.append(two_col(quantity_line, _money(item["line_total"])))
    lines.append(LINE * width)

    for group in context["tax_groups"]:
        rate = f" {_money(group['rate'])}%" if group["rate"] is not None else ""
        lines.append(f"{group['name']}{rate}")
        lines.append(two_col("  Net", _money(group["net"])))
        lines.append(two_col("  Tax", _money(group["tax"])))

    lines.append(LINE * width)
    lines.append(two_col("Subtotal", _money(context["subtotal"])))
    lines.append(two_col("Tax", _money(context["tax_amount"])))
    lines.append(two_col("TOTAL", _money(context["total_amount"])))
    lines.append(LINE * width)

    for payment in context["payments"]:
        label = f"{payment['method']} ({payment['status']})"
        lines.append(two_col(label, _money(payment["amount"])))
        if payment["provider_reference"]:
            lines.append(f"  Ref: {payment['provider_reference']}"[:width])

    lines.append(LINE * width)
    lines.append(centered("Thank you for shopping with us!"))
    lines = [line[:width] for line in lines]
    return "\n".join(lines) + "\n"
