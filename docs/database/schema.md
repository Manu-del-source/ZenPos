# Database Plan

PostgreSQL, accessed through the Django ORM.

This document is the target schema *plus* a record of how much of it exists.
The design was written before the code so the model would follow the business
rather than the screens, which means most of what follows is still planned. Read
the status table before assuming an entity is real.

## What is built, as of phase 4

| Area | State |
|---|---|
| `organizations`, `branches` | built |
| `users`, `roles`, `permissions`, `role_permissions`, `user_roles`, `user_branch_access` | built |
| `categories`, `brands`, `units`, `tax_rates`, `products`, `product_barcodes`, `price_history` | built |
| `customers` | partial — organization-scoped in phase 4; UUID key, soft deletion and the loyalty ledger arrive in phase 9 |
| `sales`, `sale_items` | **still the pre-rebuild single-branch tables** — no `branch_id`, no `till_id`, no `payments`. Phase 6 replaces them. Phase 5 added the server-captured money columns: `sale_items.unit_cost` and the per-line tax snapshot (`tax_amount`, `tax_rate_name`, `tax_rate_percent`) |
| `stock_adjustments` | interim: stock still lives in a `products.stock_level` column and movement history is an adjustment, not a ledger. Phase 7 replaces it |
| everything else below | planned, not built |

## Design rules

- **UUID primary keys**, except where a human-facing sequential number is
  needed (sale numbers, receipt numbers) — those are separate columns.
- **`created_at` / `updated_at`** on every table.
- **Soft deletion** (`deleted_at`) for masters such as products and customers.
  Financial records are never deleted at all.
- **Money is `numeric(14, 2)`**, never floating point.
- **Every stock change writes an `inventory_movements` row.** There is no code
  path that mutates stock without recording why.
- **Every loyalty change writes a `loyalty_transactions` row.**
- **Idempotency keys** protect any operation that can be retried.

## Entities

### Tenancy and organisation

```
organizations        id, name, currency (default KES), timezone, tax settings
branches             id, organization_id, name, code (unique per org), address, is_active
```

### Identity and access

```
users                id, organization_id, username, email, password_hash, is_active, last_login
roles                id, organization_id (null = system role), name, is_system
permissions          id, code (e.g. sales.refund), description
role_permissions     role_id, permission_id
user_branch_access   user_id, branch_id        (which branches a user may operate in)
user_roles           user_id, role_id, branch_id (nullable = org-wide)
```

Roles are configurable rows, not a hard-coded enum. Seeded roles:
`SUPER_ADMIN`, `ADMIN`, `MANAGER`, `SUPERVISOR`, `CASHIER`,
`INVENTORY_MANAGER`, `ACCOUNTANT`.

Permission codes are seeded by migration too (`accounts/migrations/0003_seed_rbac.py`,
extended by later migrations as the vocabulary grows — editing an applied
migration would not re-run it). A view declares the codes it demands; see
[ADR-0008](../architecture/decisions.md). Codes shipped today:
`users.manage`, `branches.manage`, `branches.view`, `settings.manage`,
`products.view|create|update`, `inventory.view|adjust|transfer`,
`purchases.create`, `sales.create|view|refund`, `customers.manage`,
`loyalty.manage`, `reports.view`.

### Catalog

```
categories           id, organization_id, parent_id, name, is_active
brands               id, organization_id, name
units                id, organization_id, name, abbreviation, allows_fraction
products             id, organization_id, name, sku, category_id, brand_id, unit_id,
                     cost_price, sale_price, tax_rate_id, low_stock_threshold,
                     track_inventory, is_active, deleted_at
product_barcodes     id, product_id, barcode (unique per organization), is_primary
price_history        id, product_id, old_price, new_price, changed_by, reason, created_at
tax_rates            id, organization_id, name, rate, is_inclusive
```

`products` is organisation-wide. `product_barcodes` is a table, so a product can
have several barcodes and barcodes are unique per organisation rather than
globally — the previous schema made `barcode` globally unique while querying it
per branch, which silently blocked two branches from stocking the same item.

### Inventory

```
branch_inventory       id, branch_id, product_id, quantity, updated_at
                       UNIQUE (branch_id, product_id)
inventory_movements    id, branch_id, product_id, delta, quantity_after,
                       reason (enum), reference_type, reference_id,
                       actor_id, notes, created_at
stock_transfers        id, from_branch_id, to_branch_id, status, requested_by,
                       approved_by, created_at, completed_at
stock_transfer_items   id, transfer_id, product_id, quantity
```

`inventory_movements` is the append-only ledger and the source of truth for stock
history. `branch_inventory.quantity` is the current snapshot and must always
equal the sum of movements for that product and branch — a reconciliation check
should assert this in CI.

### Purchasing

```
suppliers             id, organization_id, name, phone, email, address, is_active
purchase_orders       id, branch_id, supplier_id, status, ordered_by, expected_at,
                      total, created_at
purchase_items        id, purchase_order_id, product_id, quantity_ordered,
                      quantity_received, unit_cost
goods_receipts        id, purchase_order_id, branch_id, received_by, created_at
goods_receipt_items   id, goods_receipt_id, purchase_item_id, quantity, unit_cost
```

### Sales

```
sales             id, organization_id, branch_id, till_id, cash_session_id,
                  sale_number (unique per branch), cashier_id, customer_id,
                  subtotal, discount_total, tax_total, total,
                  status (DRAFT|HELD|COMPLETED|VOIDED), completed_at,
                  client_reference, created_at
sale_items        id, sale_id, product_id, quantity, unit_price, unit_cost,
                  discount_amount, tax_amount, line_total
payments          id, sale_id, method, amount, status, provider_reference,
                  received_by, created_at
payment_attempts  id, payment_id, attempt_number, provider, request_payload,
                  response_payload, status, error, created_at
returns           id, original_sale_id, branch_id, processed_by, reason,
                  status, created_at
return_items      id, return_id, sale_item_id, quantity, unit_price, line_total
refunds           id, return_id, method, amount, provider_reference,
                  authorised_by, created_at
```

`unit_cost` is captured on `sale_items` at sale time. Without it, profit cannot
be reported historically once the product's cost changes.

`payments` is a separate table rather than a column on `sales`, which is what
makes split payment, partial payment and per-method reconciliation possible.

### Tills and cash

```
tills              id, branch_id, name, code, is_active
cash_sessions      id, till_id, opened_by, closed_by, opened_at, closed_at,
                   opening_float, expected_cash, counted_cash, variance, status
cash_movements     id, cash_session_id, type (SALE|REFUND|WITHDRAWAL|ADDITION|
                   FLOAT_ADJUSTMENT), amount, reason, actor_id, created_at
```

### Customers and loyalty

```
customers            id, organization_id, name, phone, email, is_active, deleted_at
customer_loyalty     id, customer_id, points_balance, tier, updated_at
loyalty_transactions id, customer_id, sale_id, type (EARN|REDEEM|EXPIRE|ADJUST),
                     points, balance_after, reason, actor_id, created_at
```

Balances are derived from the ledger. Directly assigning a balance is prohibited
because it destroys the ability to explain why a customer has the points they do.

Phase 4 gave `customers` its `organization_id` and moved phone uniqueness from
globally unique to unique per organization, because a customer list is a phone
book of real people and one shop's staff must not read another shop's. The
integer key and single `created_at` are also deliberate for now: phase 9 rebuilds
the table with a UUID key, soft deletion and the loyalty ledger, and changing the
primary key before then would drag `sales.customer_id` and the API shape along
with it for no benefit.

### Platform

```
audit_logs       id, actor_id, action, entity_type, entity_id, branch_id,
                 before, after, ip_address, created_at
sync_events      id, branch_id, device_id, event_type, payload, status,
                 attempts, last_error, created_at, synced_at
idempotency_keys id (the key), scope, request_hash, response_body, created_at
webhook_events   id, provider, external_id (unique per provider), payload,
                 processed_at, created_at
```

`webhook_events` with a unique `(provider, external_id)` is what stops a
redelivered M-Pesa callback from paying a sale twice.

## Deferred

`mpesa_transactions`, `notifications`, `ecommerce_orders` and `etims_invoices`
are designed during their phases rather than up front. The sales domain will
interact with eTIMS only through an adapter, so compliance never leaks into the
sales engine.
