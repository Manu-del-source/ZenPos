# Phase 2 — retail operations

How the remaining back-office workflows actually run. Names and statuses match
the code, not a slide.

## Purchasing lifecycle

```
DRAFT → SUBMITTED → APPROVED → PARTIALLY_RECEIVED → RECEIVED
DRAFT / SUBMITTED / APPROVED → CANCELLED
```

- Editing is DRAFT-only.
- Approval requires `purchases.approve`.
- A posted GRN blocks cancel.

## GRN lifecycle

```
DRAFT → POSTED
DRAFT → CANCELLED
```

Inventory moves **only** on POST. Posting locks the GRN and the purchase-order
lines, refuses over-receive against live outstanding quantity, writes
`InventoryMovement` rows of type `PURCHASE_RECEIPT`, and drives the PO to
`PARTIALLY_RECEIVED` or `RECEIVED`. Repeating post is refused by status under
that lock.

Permissions: `purchases.create` drafts; `purchases.receive` posts.

## Inventory ledger

`InventoryMovement` is append-only. `BranchStock` is the live per-branch
balance. `Product.stock_level` is kept in step so the existing POS path still
reads a number.

Every stock-changing workflow calls `inventory.services.apply_stock_movement`.
Sales still write a compatibility `StockAdjustment` (notes prefixed with the
sale number) so void/restore remains idempotent.

## Transfer lifecycle

```
DRAFT → REQUESTED → APPROVED → DISPATCHED → IN_TRANSIT → RECEIVED
DRAFT / REQUESTED / APPROVED → CANCELLED
```

Dispatch decrements the source (`TRANSFER_OUT`). Receive increments the
destination (`TRANSFER_IN`). Partial receive leaves the transfer `IN_TRANSIT`.
Over-receive is refused. Duplicate dispatch/receive is refused by status.

## Returns & refunds

```
REQUESTED → AUTHORIZED → COMPLETED
REQUESTED → REJECTED
REQUESTED / AUTHORIZED → CANCELLED
```

Cashiers hold `returns.request`. Completing a refund needs `sales.refund`.
Quantity cannot exceed sold minus already returned. Completing writes a
`RETURN` (and `DAMAGE` if not restocked) movement and a `Payment` in
`REFUNDED` status. Repeating complete is a no-op.

## Staff

`Employee` is the HR record (number, status, start date, optional user link).
`User` remains the login. Status changes are audited as `staff.status_changed`.

## Loyalty ledger

`LoyaltyRule` (points per KES) → `LoyaltyAccount` (transactional balance) →
`LoyaltyLedger` (EARN / REDEEM / ADJUST / REVERSAL / EXPIRE).

A completed sale awards points once (`uniq_loyalty_org_action_ref`). A
completed return reverses that earn once. Redeem refuses a negative balance.

## Permission matrix (codes as seeded)

| Role | Characteristic grants |
|---|---|
| CASHIER | `sales.create`, `sales.view`, `customers.manage`, `returns.request`, `inventory.view` |
| SUPERVISOR | cashier + `sales.refund`, `inventory.adjust` |
| MANAGER / INVENTORY_MANAGER | purchasing, receiving, transfers, reports, staff (`users.manage`), loyalty |
| ADMIN / SUPER_ADMIN | organization-wide, including `branches.manage` |

Enforcement is `HasPermission` plus `OrganizationScopedMixin` /
`BranchScopedMixin`. Hiding a button is never the control.
