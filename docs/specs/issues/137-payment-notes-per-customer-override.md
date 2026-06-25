## Overview

Add an optional customer-level payment notes override for invoice payment instructions. The new field appears in `Customer details > Edit > Billing defaults` as a textarea. When rendering invoice payment notes, customer-specific notes take precedence; otherwise invoices fall back to the issuer company’s existing payment notes.

## Problem

Payment notes are currently stored only on the issuer company account (`Company.payment_terms`) and rendered on invoices for all customers. Some customers need different payment notices because of country-specific payment instructions. There is no per-customer override, so operators must either use one generic account-wide note or manually work around the limitation outside the customer profile.

## Proposed Outcome

Customers gain a blank-by-default `payment_notes` textarea in the Billing defaults block of the customer Edit tab. Invoice PDF preview/generation resolves payment notes in this order:

1. Customer payment notes when the selected invoice customer has non-empty notes.
2. Issuer company payment notes when the customer notes are empty.
3. No Payment Notes block when both values are empty.

Assumption: the visible field label should be `Payment notes`, matching the existing issuer company settings label.

## Constraints / Non-Goals

- Do not add an invoice-level payment notes editor or snapshot in this task; follow the existing render-time behavior used for company payment notes.
- Do not change bank account selection, payment period logic, or invoice due-date calculations.
- Do not display an empty `Payment Notes` heading when no customer or company notes are available.
- Do not add automation-only product behavior, hidden routes, or seeded-only UI paths to support evidence capture.

## Acceptance Criteria

### User Outcome

1. A user can open a customer profile, choose the Edit tab, and see a `Payment notes` textarea inside the Billing defaults block beneath the existing currency/payment period controls.
2. A user can save customer-specific payment notes and see the value persist after the customer page reloads.
3. Invoice PDF preview/generated invoices for that customer show the customer-specific payment notes instead of the issuer company default notes.
4. Customers without custom payment notes continue to use the issuer company default payment notes.
5. When both customer and issuer company payment notes are empty, invoices omit the Payment Notes section entirely.

### Technical Behavior

1. `Customer` stores the new optional payment notes value in the database with a migration and no required backfill.
2. Whitespace-only customer payment notes are treated as empty for fallback/rendering.
3. Customer edit POST handling saves the new field together with existing billing defaults.
4. All invoice PDF render paths that use `invoices/invoice_pdf.html` receive the same resolved payment notes value.
5. The existing issuer company payment notes field remains unchanged and continues to work as the default fallback.

### Operations / Deployment

1. The deployment applies one additive Django migration for the new nullable/blank customer field.
2. Existing customers remain valid and behave as before until a custom customer payment note is added.
3. No manual data migration is required.

### Validation

1. Django tests cover saving customer payment notes through the customer profile edit flow.
2. Django tests cover invoice payment note precedence: customer override, company fallback, and no-section behavior when both are blank.
3. Existing customer, company, and invoice tests continue to pass.
4. Preview-safe demo and visual validation scripts are updated for this issue’s evidence paths.

## Demo Media

### Scenario: customer-payment-notes-override

#### Repo Command

./scripts/demo-evidence.sh customer-payment-notes-override

#### Outputs

video + screenshots

#### Steps

1. Open an active customer profile in the app and switch to the Edit tab.
2. Enter and save a customer-specific payment note in the Billing defaults Payment notes textarea.
3. Open an invoice PDF preview for that customer and leave the preview in a reviewer-visible state where the Payment Notes section reflects the customer override.

#### Screenshot Checkpoints

- customer-payment-notes-edit: full-page screenshot of the customer Edit tab after the Billing defaults note has been saved
- customer-payment-notes-pdf: full-page screenshot of the invoice PDF preview showing the resolved Payment Notes section

## Visual Validation

### Identifier

customer-payment-notes-billing-defaults

### Capture Command

./scripts/visual-validation.sh customer-payment-notes-billing-defaults

### Steps

1. Open an active customer profile and switch to the Edit tab.
2. In baseline mode, capture the existing customer Edit tab Billing defaults area without requiring the new textarea.
3. In current mode, open the same customer Edit tab and verify the Payment notes textarea is present before capture.

### Full-Page Checkpoints

- customer-edit-billing-defaults: full-page screenshot of the customer Edit tab with the Billing defaults block visible

### Expected Comparisons

- The `customer-edit-billing-defaults` baseline/current pair should show the Billing defaults block gaining a Payment notes textarea while preserving the surrounding customer edit layout.

## Implementation Plan

1. Add an optional `payment_notes` text field to `Customer` and generate the corresponding Django migration.
2. Extend `CustomerBillingForm` to include the new field, configure it as a textarea, and keep it optional.
3. Render the new field in the customer profile Edit tab Billing defaults block, including the HTMX partial used for edit-tab refreshes if that path is still supported.
4. Update customer edit save handling so the new field is persisted in the same flow as currency and payment period.
5. Centralize invoice payment note resolution so invoice PDF preview and generated PDF paths share the same customer-override/company-fallback behavior.
6. Update `invoice_pdf.html` to render the resolved payment notes value and suppress the Payment Notes block when the resolved value is empty.
7. Add focused Django tests for form persistence and invoice note fallback behavior.
8. Add/update Playwright evidence wiring for the declared demo and visual validation identifiers.

## Task List

- [x] Add customer payment notes storage and form support
  - [x] Add `payment_notes` to `Customer` with blank/empty-safe defaults.
  - [x] Generate the next `invoices` migration for the new field.
  - [x] Include `payment_notes` in `CustomerBillingForm`.
  - [x] Configure the form field as an optional textarea labeled `Payment notes`.

- [x] Update customer edit UI and save flow
  - [x] Add the Payment notes field to the Billing defaults block in `customer_profile.html`.
  - [x] Keep the HTMX customer edit partial aligned with the main edit form if it remains in use.
  - [x] Ensure the customer profile POST save updates the new field with the other billing defaults.
  - [x] Add customer view/form tests for saving and reloading the payment notes value.

- [x] Apply payment note fallback to invoice rendering
  - [x] Add a shared resolver for invoice payment notes with customer override, company fallback, and empty suppression.
  - [x] Pass the resolved value into PDF preview and generated PDF contexts.
  - [x] Update `invoice_pdf.html` to use the resolved value for Payment Notes rendering.
  - [x] Add tests for customer override, company fallback, and no Payment Notes block when both sources are empty.

- [ ] Add issue-specific reviewer evidence hooks
  - [ ] Add a Playwright scenario for the customer payment notes override demo using real UI flows.
  - [ ] Wire `customer-payment-notes-override` into `scripts/demo-evidence.sh`.
  - [ ] Add baseline/current-safe visual capture for the customer edit Billing defaults block.
  - [ ] Wire `customer-payment-notes-billing-defaults` into `scripts/visual-validation.sh`.

## Deployment / Rollout

- Deploy with the additive Django migration before users save customer payment notes.
- Existing invoice rendering continues to use issuer company payment notes until customer overrides are populated.
- No production data backfill is required.
- Validate after deployment by editing a non-critical customer with a custom note, previewing an invoice for that customer, and confirming customers without overrides still use the company default.

## File-Level Changes

### Add

- `invoices/migrations/0066_customer_payment_notes.py` or the next makemigrations-generated migration.
- A focused Playwright evidence spec if no existing spec cleanly fits the declared demo/visual identifiers.

### Modify

- `invoices/models.py`
- `invoices/forms.py`
- `invoices/views.py`
- `invoices/templates/invoices/customer_profile.html`
- `invoices/templates/invoices/partials/customer_edit_form.html`
- `invoices/templates/invoices/invoice_pdf.html`
- `invoices/tests/test_customers.py`
- `invoices/tests/test_invoices.py`
- `scripts/demo-evidence.sh`
- `scripts/visual-validation.sh`

### Keep

- Existing issuer company `Company.payment_terms` field and company settings behavior.
- Existing bank account and payment period behavior.
- Existing invoice notes/project comments behavior, which is separate from payment notes.

## Open Questions

None.
