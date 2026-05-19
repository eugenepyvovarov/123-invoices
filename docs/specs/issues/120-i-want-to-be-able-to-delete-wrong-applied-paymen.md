## Overview

Add an invoice-scoped way to remove a payment that was applied to the wrong invoice, with an explicit confirmation before the removal completes.

## Problem

Payments can be applied to invoices, and existing customer/project payment screens can delete whole payment records. The invoice detail view shows applied payments but does not provide a direct, invoice-scoped way to remove an incorrect application. When a payment is applied to the wrong invoice, the invoice can remain incorrectly paid or partially paid, which affects outstanding amounts, invoice status, and reporting.

## Proposed Outcome

Add a confirmed “remove from invoice” action in the invoice Payments table.

The recommended cut is to remove only the `PaymentApplication` linking the payment to the current invoice, not the underlying received `Payment` record. This keeps payment receipt history intact and lets the user reapply or edit the payment separately through existing payment flows.

If the removed application was the payment’s last application, keep the `Payment` record and mark it as pending/unapplied. Existing customer/project payment deletion remains the destructive way to delete the payment record itself.

## Constraints / Non-Goals

- Do not add a new payment model or database migration unless implementation finds an unavoidable schema gap.
- Do not remove or change the existing customer/project-level whole-payment Delete action.
- Do not add bulk payment unapply behavior.
- Do not redesign the payment drawer or invoice preview layout beyond the new invoice-scoped remove action.
- Use CSRF-protected POST for removal; GET requests must not mutate payment data.
- Keep monetary display at two decimals.
- If icons are added, use Tabler Icons only.

## Acceptance Criteria

### User Outcome

1. An invoice with applied payments shows a clear invoice-scoped action to remove an applied payment from that invoice.
2. Activating the action asks for confirmation before any data is changed.
3. Cancelling the confirmation leaves the payment application, invoice totals, and invoice status unchanged.
4. Confirming the removal updates the invoice view so the payment is no longer shown as applied to that invoice and the outstanding amount/status reflects the removal.

### Technical Behavior

1. The removal deletes only the selected `PaymentApplication` for the active issuer and current invoice.
2. The underlying `Payment` record is preserved.
3. If the payment still has other applications, those applications remain unchanged and the payment stays applied.
4. If the payment has no remaining applications, the payment is marked pending/unapplied.
5. Invoice cached totals are recalculated, including `amount_paid`, `amount_due`, `amount_overdue`, `last_payment_date`, and status normalization.
6. The affected invoice PDF refresh is attempted consistently with existing payment add/delete flows and does not block removal if PDF generation is unavailable.
7. Cross-company or wrong-issuer removal attempts are rejected by the same active-issuer scoping used elsewhere.

### Operations / Deployment

1. No data migration is expected.
2. Standard deploy/build behavior is sufficient; static assets are collected if a JavaScript file changes.
3. Existing payment records remain valid after deployment.
4. Dashboard cache for the affected issuer is invalidated after successful removal.

### Validation

1. Django tests cover successful removal, cancellation/no-op behavior where practical, wrong-issuer protection, POST-only mutation, single-application payment status changes, and multi-application preservation.
2. Playwright coverage exercises the visible invoice flow: applied payment visible, confirmation cancelled, confirmation accepted, and final invoice state updated.
3. Demo and visual evidence use the issue-specific commands declared in this spec.

## Implementation Plan

1. Add an invoice-scoped POST endpoint that receives the invoice id and payment application id, scopes both through the active issuer, and rejects mismatches.
2. In a transaction, delete the selected `PaymentApplication`, update the related `Payment.status` based on remaining applications, and collect the affected invoice/payment ids for post-transaction work.
3. Recalculate invoice cached amounts through the existing invoice-total pathway, invalidate dashboard cache, and refresh the affected invoice PDF using the existing non-blocking pattern.
4. Add a remove action to each invoice payment row in `invoice_profile.html`, keeping the existing Open/Edit payment behavior.
5. Add confirmation behavior for the new action and return either JSON for XHR or a safe redirect back to the invoice preview for normal form submission.
6. Add targeted Django and Playwright tests for the backend behavior and visible invoice workflow.

## Task List

- [x] Add invoice-scoped payment application removal behavior
  - [x] Add a POST-only URL and view for removing a payment application from a specific invoice.
  - [x] Scope the invoice and payment application by active issuer and current invoice before mutation.
  - [x] Delete only the selected application and preserve the underlying payment record.
  - [x] Update payment status to pending when no applications remain, or applied when other applications remain.
  - [x] Recalculate affected invoice totals/status, invalidate dashboard cache, and refresh the invoice PDF non-blockingly.
  - [x] Add Django tests for success, wrong issuer, POST-only behavior, single-application, and multi-application cases.

- [x] Update the invoice payments table UI
  - [x] Add a clear “remove from invoice” action beside existing payment actions in the invoice Payments table.
  - [x] Add confirmation handling so cancel prevents the request and confirm submits the removal.
  - [x] Keep existing Add payment and Open/Edit payment controls working unchanged.
  - [x] Preserve two-decimal amount formatting and current table layout conventions.

- [x] Add preview-safe browser coverage and evidence capture
  - [x] Add an issue-specific Playwright scenario that reaches an invoice with an applied payment.
  - [x] Cover cancelling the confirmation and confirming the removal.
  - [x] Capture the declared before/after demo screenshots from stable invoice preview states.
  - [x] Capture the declared visual-validation checkpoint for the payment action layout.

## Deployment / Rollout

No migration or backfill is expected. Deploy through the standard Django path and collect static assets if JavaScript changes. After rollout, users can remove wrong invoice applications directly from invoice detail pages; any accidental removal can be corrected by reapplying or editing the preserved payment record.

Rollback removes the UI and endpoint but does not recreate applications already removed by users. Because the action is confirmed and invoice-scoped, no manual rollout gate is required beyond the normal test pass.

## File-Level Changes

### Add

- `tests/e2e/payment-application-remove.spec.js` — issue-specific browser coverage and evidence capture for removing an applied payment from an invoice.

### Modify

- `invoices/urls.py` — add the invoice-scoped payment application removal route.
- `invoices/views.py` — add the removal view, status updates, cache invalidation, PDF refresh, and safe response behavior.
- `invoices/templates/invoices/invoice_profile.html` — add the remove action to applied payment rows.
- `invoices/static/invoices/js/payment_drawer.js` or a focused invoice payment applications script — add confirmation/AJAX handling for the new action.
- `invoices/tests/test_invoices.py` — add targeted backend coverage for payment application removal.

### Keep

- Existing `Payment` and `PaymentApplication` models unless implementation finds an unavoidable issue.
- Existing customer/project-level whole-payment Delete behavior.
- Existing payment drawer add/edit behavior.
- Existing invoice PDF template layout.

## Demo Media

### Scenario: invoice-payment-application-remove

#### Repo Command

PLAYWRIGHT_VIDEO=on OPENCODE_DEMO_SCENARIO=invoice-payment-application-remove ./scripts/e2e.sh tests/e2e/payment-application-remove.spec.js --project=chromium

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open an invoice preview state with an applied payment, applying a small payment through the existing drawer first if needed.
3. Show the invoice Payments table with the invoice-scoped remove action visible.
4. Trigger the remove action, accept the confirmation, and wait for the invoice preview to refresh.
5. Leave the UI on the invoice preview showing the payment no longer applied to that invoice and the outstanding state available for review.

#### Screenshot Checkpoints

- invoice-payment-remove-before-full-page: full-page screenshot of the invoice preview with an applied payment row and remove action visible
- invoice-payment-remove-after-full-page: full-page screenshot of the invoice preview after confirmed removal, showing the updated applied-payment/outstanding state

## Visual Validation

### Identifier

invoice-payment-application-remove-ui

### Capture Command

./scripts/e2e.sh tests/e2e/payment-application-remove.spec.js --project=chromium

### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open an invoice preview state with an applied payment and capture the full page with the Payments table action area visible.

### Full-Page Checkpoints

- invoice-payment-actions-full-page: full-page screenshot of the invoice preview with the applied payment row and invoice-scoped action area visible

### Expected Comparisons

- The `invoice-payment-actions-full-page` baseline/current pair should show a clear invoice-scoped remove action added to the Payments table without unrelated invoice preview layout changes.

### Baseline SHA

`789390b51e359883c325559b7b80f6bc3f165ccb`


## Open Questions

None.
