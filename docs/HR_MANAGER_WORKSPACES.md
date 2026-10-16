# HR and Manager Workspaces

## Goal

Provide distinct, permission-aware workspaces for the HR Manager and Manager roles using the existing ZenPOS API. A dashboard card or navigation link is not proof that a workflow exists: a feature is complete only when its data model, API, server-side authorization, frontend workflow, audit behavior, and tests are in place.

## Current implementation in this branch

- HR Manager and Manager accounts are routed to the dashboard after successful login.
- The dashboard navigation label reflects the role.
- HR Manager receives an HR workspace showing counts derived from existing employee and branch endpoints.
- The HR workspace links to the existing employee directory and explicitly identifies HR workflows that are not yet implemented.
- The Manager continues to use the existing operational dashboard and permission-filtered navigation.
- This change does not alter production data, role grants, or backend permissions.

## HR Manager scope

### Available now
- Employee directory: create, search, update and maintain existing employee records.
- Employee status: active, inactive, suspended and terminated records.
- Branch assignment and role linkage as allowed by the existing employee management API.
- Existing staff-account operations only where current server permissions allow them.

### Required future workflows
1. **Employment lifecycle:** job title, department, employment type, contract and probation dates, reporting line, emergency contact, document checklist, onboarding and offboarding.
2. **Attendance and shifts:** schedules, clock-in/out records, lateness, absences, correction requests, overtime and manager review.
3. **Leave management:** leave types, balances, requests, approval/rejection, cancellation, calendar and audit history.
4. **Recruitment:** vacancies, candidate records, interview stages, offer decisions and onboarding conversion.
5. **Performance and development:** review cycles, goals, review notes, training, skills and certification expiry.
6. **Employee relations:** restricted case records, grievance/disciplinary workflows, assigned follow-ups and access logging.
7. **Payroll preparation:** approved attendance/overtime/leave inputs, payslip-period status and export/reconciliation. Salary, bank and statutory data must be separately permissioned; tax calculations and payroll execution require their own validated scope.
8. **HR reporting:** headcount, status, absence, leave utilization, turnover, onboarding completion, training and review completion.

HR must not gain unrestricted access to sales reports, business financial settings, payment-provider credentials, organization security settings or custom-role permission delegation merely because it manages staff.

## Manager scope

1. **Daily operations:** sales and transaction monitoring, till status, exceptions and operational handovers.
2. **People supervision:** assigned-branch staff visibility, shift coordination, task allocation, attendance exceptions and staffing requests. HR owns confidential employee cases and HR records.
3. **Sales and customers:** authorized sales/receipt lookup, customer records, returns/refunds within policy and exception escalation.
4. **Inventory:** stock availability, low-stock actions, counts, adjustments and transfers subject to permission and branch scope.
5. **Purchasing:** purchase requests/orders, supplier coordination, receiving and approval separation where configured.
6. **Branch performance:** branch-scoped sales, inventory, purchasing and operational reports.
7. **Compliance and audit:** relevant eTIMS status, till discrepancies, stock variance, and review of audit events permitted to the manager.
8. **Team access:** request or administer ordinary staff access only where delegated; never grant self-privileges or assign platform super-administrator access.

## Authorization and data rules

- Server-side permission checks remain authoritative; frontend navigation is only a usability layer.
- Every query and mutation must enforce organization/tenant boundaries and branch scope.
- HR-only data (disciplinary cases, health/accommodation documents, salary and bank details) must be minimized and separately authorized.
- High-impact actions need audit records with actor, timestamp, target and before/after values where appropriate.
- Financial and stock ledgers must use the existing correction/reversal patterns; do not silently rewrite historical records.
- Separate request and approval permissions for sensitive actions; no self-approval for actions that need independent control.
- Never display placeholder metrics or mark planned workflows as available.

## Delivery sequence

1. Stabilize role-specific routing and dashboards using existing endpoints.
2. Add and test attendance, shifts and leave with explicit permission codes and approval rules.
3. Add employment lifecycle and document access controls.
4. Add recruitment, onboarding, performance and training.
5. Add confidential employee-relations cases and access auditing.
6. Add payroll preparation and HR reports only after data protection, calculation, and authorization requirements are defined.
7. Expand Manager workflows around operational exceptions and delegated approvals, with branch-scoped tests.

Each phase must be reviewed on staging before any production merge or deployment.
