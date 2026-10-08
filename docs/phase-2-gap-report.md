# Phase 2 gap report

Inspected against commit `0455489` (`Add purchase orders as the second purchasing vertical slice`).
This is a snapshot of what the rebuild already has, before the remaining
retail-operations slices are built. Nothing in this file is a promise that a
page exists — a workflow is only **IMPLEMENTED** when models, API, permissions,
audit, tests and a connected front-end all exist.

## Summary

| Area | Status |
|---|---|
| Goods receiving / GRN | **MISSING** |
| Inventory ledger | **PARTIAL** |
| Stock transfers | **MISSING** |
| Returns & refunds | **PARTIAL** |
| Branch management | **PARTIAL** |
| Staff / employee | **PARTIAL** |
| Loyalty | **PARTIAL** |
| Front-office integration | **PARTIAL** |
| Back-office reporting | **PARTIAL** |
| Permissions | **IMPLEMENTED** (extend, do not replace) |
| Audit logging | **IMPLEMENTED** (reuse `core.audit.record_audit`) |
| Tests | **PARTIAL** (existing slices covered; new slices absent) |

---

## GRN — MISSING

Purchase orders already carry `PARTIALLY_RECEIVED` / `RECEIVED` statuses and
document that receiving will drive them. There is no Goods Received Note model,
no received-quantity on PO lines, no post/cancel API, no inventory effect on
receipt, and no receiving screen. The PO page has no **Receive Goods** action.

## Inventory ledger — PARTIAL

`StockAdjustment` is an append-only *why* record (no update/delete) and is the
seed the architecture notes point at. It is not the ledger the brief asks for:

- no organization / branch
- no before / after quantity
- no reference type / id
- movement types do not match the ledger vocabulary
- `Product.stock_level` is still a mutable org-wide integer, not per-branch
- sales, voids and adjustments write `StockAdjustment` rows; nothing else does

Needs: immutable `InventoryMovement`, per-branch `BranchStock` as the live
balance, and every stock-changing workflow writing a movement.

## Stock transfers — MISSING

`inventory.transfer` is seeded on MANAGER / INVENTORY_MANAGER. No model, API,
or UI. Inter-branch movement cannot happen until per-branch stock exists.

## Returns & refunds — PARTIAL

A completed sale can be **voided** (`sales.refund`): payments marked REFUNDED,
stock restored via `StockAdjustment`, sale kept. That is a full-sale reversal,
not a retail return:

- no per-line return quantity
- no request → authorize → refund workflow
- no reason codes
- no partial return
- no duplicate-item protection beyond “void is idempotent”
- POS / sales history has no Return Items action

## Branch management — PARTIAL

`Branch` has name, code, address, phone, active flag, organization.
`UserBranchAccess` and `UserRole.branch` already enforce *where*. Backend
scoping (`BranchScopedMixin`) is real. Gaps:

- no manager assignment
- no timezone on the branch (organization has one)
- Settings page does not manage branches or branch users
- cross-branch tests exist for sales/branches; new workflows must add their own

## Staff / employee — PARTIAL

`accounts.User` is the staff account (org, default branch, roles, branch
access). There is no employee record: no employee number, employment status,
start date, or user↔employee link separate from the login account. The user
admin API exists; there is no Staff screen.

## Loyalty — PARTIAL

`Customer.loyalty_points` is a mutable integer, **read-only** on the API, with
an explicit comment that phase 8 replaces it with a ledger. No account, no
ledger, no earn-on-sale, no redeem, no reversal on return, no configurable
points rule, no UI.

## Front-office integration — PARTIAL

POS already lets the server own price, tax, stock check, totals, cash and
M-Pesa. It does not yet:

- read per-branch stock
- write the inventory ledger on sale
- award loyalty points
- expose return eligibility

Do not rebuild checkout; connect it.

## Back-office reporting — PARTIAL

`/analytics/` exposes daily sales trend, stock value, low stock, inventory
status. `/sales/reports/` is a short-range summary. Missing purchasing,
receiving, transfers, adjustments, returns, loyalty, and branch performance.
All of it must stay server-filtered and paginated.

## Permissions — IMPLEMENTED (extend)

Single vocabulary, seeded in `accounts` migrations, enforced by `HasPermission`.
Existing codes already cover most of the matrix (`purchases.create` even says
“receive goods”). Add only the codes a new door needs (`purchases.receive`,
`returns.request`). Do not invent a second RBAC.

## Audit — IMPLEMENTED

`modules.core.audit.record_audit` inside the same transaction as the change.
New workflows must call it. Do not add another log.

## Tests — PARTIAL

Strong characterization around auth, RBAC, catalogue, sales, payments, POs,
suppliers, adjustments, branch isolation. Every new vertical slice needs the
same shape: happy path, validation, permission, cross-tenant, duplicate,
concurrency, audit, inventory, money.

---

## Implementation order (as specified)

1. Goods receiving / GRN (this slice first)
2. Inventory ledger (complete the movement architecture GRN posting uses)
3. Stock transfers
4. Returns & refunds
5. Branch management completion
6. Staff / employee foundation
7. Loyalty foundation
8. Front-office integration
9. Back-office reporting
10. UX / docs / final audit
