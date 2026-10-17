# M-Pesa Manual Till Reconciliation — Implementation Specification

## Reference model

Use Moneta Pay's documented M-Pesa workflow as the product behavior reference: verified incoming payments enter an unmatched queue; the cashier can manually assign an unmatched payment to an open order; successful assignment updates the order; unmatched and ambiguous cases remain reviewable.

Use Safaricom Daraja's official C2B API as the provider contract reference. Register the C2B validation and confirmation URLs for the configured shortcode and environment. Treat C2B confirmation as the source of incoming Till/Paybill transaction records. Do not use TransactionStatusQuery as a transaction-discovery/search API: it verifies a known transaction using an identifier. Use transaction-pull only if the merchant's Daraja product/access supports it and its response can be validated.

References:
- Moneta Pay M-Pesa integration: https://docs.moneta-pay.app/features/mpesa
- Safaricom Daraja C2B API: https://developer.safaricom.co.ke/apis/CustomerToBusiness
- Safaricom Transaction Status API: https://developer.safaricom.co.ke/apis/TransactionStatus

## Scope

This feature supplements, and must not regress, the existing STK Push flow. Manual Till payments are a separate incoming-payment path. Keep the existing Payment/PaymentAttempt/WebhookEvent behavior for STK unless a migration is explicitly tested.

## Data model requirements

Create a durable incoming Till transaction ledger, separate from STK PaymentAttempt:
- provider and merchant shortcode/account configuration identity;
- unique provider receipt/TransID (unique within provider/merchant scope);
- amount in KES using Decimal;
- transaction timestamp supplied by Safaricom;
- payer phone and payer name when supplied, with least-privilege access and masked display;
- bill reference/account reference and third-party transaction ID where supplied;
- raw callback payload restricted to operational/audit access;
- state: UNMATCHED, MATCHED, DUPLICATE_REVIEW, or REJECTED;
- matched sale/payment, matched-by user, matched-at timestamp, and audit metadata.

Enforce database uniqueness for provider receipt identity and an atomic claim/assignment operation. A callback replay must not create a second transaction or apply a second settlement.

## C2B callback contract

- Add anonymous Safaricom-facing C2B validation and confirmation endpoints at separately configured public URLs.
- Validate the callback shape and required fields; bind each callback to the expected merchant shortcode and environment.
- Store confirmation events idempotently and durably before returning success.
- Never log callback secrets, access tokens, full payer data, or sensitive payloads.
- Handle duplicate callbacks safely and return the response format required by the Daraja C2B contract.
- Do not mark a sale paid from a client-supplied receipt, amount, or phone number.
- A successful C2B confirmation proves money was received by the merchant; it does not by itself identify the sale.

## Cashier matching behavior

Add a permission-protected “Match Till Payment” flow:
1. Default the amount filter to the selected sale's outstanding balance.
2. Show recent UNMATCHED payments for the current merchant/organization/branch, filtered by amount and a configurable time window.
3. Display amount, transaction time, receipt/TransID, masked payer phone, payer name if available, bill reference, and status.
4. If exactly one candidate exists, show its details and require cashier confirmation; do not silently guess.
5. If multiple candidates exist (including two KES 500 payments), require the cashier to verify receipt ID, time, payer phone/name, or bill reference and select one explicitly.
6. If no candidate exists, keep the sale pending and offer refresh/retry; never manufacture a payment record from the customer's claim.
7. Re-check amount, merchant scope, status, sale outstanding balance, and assignment state inside a database transaction with row locking before matching.
8. Prevent overpayment/underpayment unless explicit split/partial-payment rules permit it. Never allow a transaction to be matched to two sales.
9. Record an append-only audit event including actor, sale, transaction receipt, amount, and timestamp.
10. Keep customer phone display masked by default; reveal more only to authorized roles when necessary.

## Reliability and security

- Organization, branch, register, and cashier authorization must be enforced server-side on every list/search/match endpoint.
- Use database transactions and uniqueness constraints for concurrent callbacks and cashier claims.
- Treat amount/time as candidate filters, not proof of identity.
- Make callbacks idempotent; test retries, duplicate TransID, malformed payloads, out-of-order delivery, unknown shortcode, wrong environment, and database errors.
- Use a background reconciliation job only for known transaction identifiers; never assume TransactionStatusQuery can search a Till by amount.
- Add retention and access controls for raw payloads and payer information.
- Add monitoring for callback failures, unmatched queue age, duplicate receipts, and failed matching attempts.

## Acceptance tests

1. Two different KES 500 transactions appear as separate unmatched rows with distinct receipt IDs.
2. A cashier can match only the selected receipt to the intended eligible sale.
3. A second cashier cannot claim the same receipt concurrently; exactly one claim succeeds.
4. Replaying the same C2B callback creates no duplicate ledger row and no second settlement.
5. A transaction from another merchant/organization cannot be listed or attached.
6. Amount mismatch, already-matched transaction, refunded/rejected transaction, and closed/void sale are rejected.
7. Payer details are masked for normal cashier display.
8. Existing STK Push success, failure, timeout, duplicate callback, and polling tests still pass.
9. C2B callback tests use fixtures/mocks; CI must never call Safaricom live.
10. Sandbox callback registration and a controlled production smoke test are documented before enabling the feature for all cashiers.

## Rollout gates

- Implement on `feat/mpesa-till-reconciliation`, not directly on production.
- Run migrations and the full backend/frontend test suites.
- Test sandbox callback delivery and duplicate delivery.
- Verify production Daraja app permissions, shortcode type, validation/confirmation URLs, HTTPS reachability, environment variables, and merchant ownership before live rollout.
- Enable behind a feature flag or organization-level setting; monitor before broad release.
- Do not claim production readiness until the controlled live transaction and operational recovery procedures are verified.
