## Overview

Add multi-bank-account support for each issuing company, with one default account and an invoice-level account selection that can follow the account last used for the same client.

Assumption: “company” means the active issuing company, not client companies, because invoice PDFs currently render the issuer company’s bank information.

## Problem

The app currently stores one freeform bank account field on `Company` and renders that issuer-level value on invoices. That prevents an issuing company from using different bank accounts for different clients or changing the account on a single invoice without changing all future renders that use the company record.

## Proposed Outcome

1. Each issuing company can manage multiple bank accounts from Company information.
2. When an issuing company has bank accounts, exactly one active account is the default.
3. Each invoice stores the selected bank account.
4. New invoices default to:
   - the active bank account used on the most recent saved invoice for the selected client, when available;
   - otherwise the issuing company’s default active bank account.
5. Users can override the selected bank account on invoice create/edit.
6. Invoice preview/PDF rendering uses the invoice’s selected bank account.

## Constraints / Non-Goals

- Do not add receiving/client bank account management.
- Do not add an explicit customer-level bank account preference in this cut; per-client behavior comes from the last saved invoice for that client.
- Do not change invoice totals, order-line behavior, payment terms, payment notes, or payment recording.
- Do not validate IBAN/SWIFT formats beyond normal required/blank field validation.
- Keep existing single bank account data through migration/backfill; do not drop or lose existing payment information.
- Use Tabler icons only if new UI icons are added.

## Acceptance Criteria

### User Outcome

1. A user can add, edit, deactivate, and mark a default bank account for the active issuing company.
2. A user can see which bank account is the default in Company information.
3. A user can create a new invoice and see a bank account selector in the invoice form.
4. When the selected client has a previous invoice with an active bank account, the new invoice defaults to that account.
5. When the selected client has no previous active account, the new invoice defaults to the issuing company default.
6. A user can change the selected account before saving an invoice.
7. Invoice preview/PDF payment information shows the selected invoice account, not always the company default.

### Technical Behavior

1. Bank accounts are scoped to the active issuer/issuing company and cannot be assigned across issuers.
2. The database and forms enforce at most one default bank account per issuer.
3. The company settings save path validates that an issuer with active bank accounts has one active default.
4. Existing `Company.bank_account_number` and payment method data are backfilled into a default issuer bank account.
5. Existing invoices are backfilled to the issuer default account where possible.
6. Invoice create/edit/drawer/quick-save/autosave paths persist the selected bank account consistently.
7. Bulk last-month invoice creation copies the previous invoice’s account for that project/client when available, otherwise uses the issuer default.
8. Imported invoices that do not provide bank account data use the issuer default.
9. Inactive accounts remain renderable for invoices already linked to them but are not offered as defaults for new invoices.

### Operations / Deployment

1. Django migrations create the bank account model and invoice foreign key.
2. Data migration is idempotent and safe for companies with blank existing bank account fields.
3. No new environment variables or operator secrets are required.
4. Normal migration and static collection steps are sufficient for rollout.
5. Stored PDF files are not bulk-regenerated during deployment; newly generated previews/PDFs use the selected account.

### Validation

1. Django model/form tests cover default enforcement, issuer scoping, inactive accounts, and migration backfill.
2. Django view tests cover company settings bank account management.
3. Django invoice tests cover create/edit defaults, manual override, bulk last-month creation, and PDF context rendering.
4. Existing invoice, company, and import tests continue to pass after the model changes.
5. Playwright coverage captures preview-safe reviewer evidence for company account management, invoice account selection, and invoice preview/PDF payment details.

## Implementation Plan

1. Add an `IssuerBankAccount` model with issuer, label, payment method, account details, default flag, active flag, sort order, and timestamps.
2. Add a nullable protected `bank_account` foreign key to `Invoice`.
3. Add migrations to create issuer bank accounts from existing company bank details and backfill invoices to the issuer default where possible.
4. Update admin and query helpers to expose issuer bank accounts safely.
5. Replace the single bank account field in Company information with a bank-account formset/table that supports multiple active accounts and one default.
6. Add invoice-bank-account resolution helpers for “last account used by this customer, else default”.
7. Add a scoped `bank_account` field to `InvoiceForm` and wire it through invoice create, edit, drawer, quick-save, autosave, bulk creation, and imports.
8. Add client-side form behavior so changing the selected project can update the suggested bank account unless the user has manually overridden it.
9. Update invoice preview/PDF templates to render the selected invoice account while preserving company payment notes.
10. Add Django and Playwright coverage for the new persistence, UI, defaulting, and rendering behavior.

## Task List

- [x] Add bank account persistence and backfill
  - [x] Add `IssuerBankAccount` or equivalent issuer-scoped model with default/active fields and a one-default constraint.
  - [x] Add `Invoice.bank_account` with protected nullable relation.
  - [x] Create migrations that backfill issuer default accounts from existing company bank details.
  - [x] Backfill existing invoices to the issuer default account where available.
  - [x] Add model/admin tests for default enforcement, issuer scoping, and inactive linked accounts.

- [x] Build company bank account management
  - [x] Add forms/formset for account label, payment method, account details, active state, sort order, and default selection.
  - [x] Replace the Finance single bank account field with multi-account management in `company_settings.html`.
  - [x] Save company, address, issuer settings, and account changes atomically.
  - [x] Validate one active default when active accounts exist.
  - [x] Add company settings view tests for add/edit/default/deactivate behavior.

- [x] Wire invoice account selection and rendering
  - [x] Add invoice account resolver helpers for customer last-used account fallback to issuer default.
  - [x] Add the scoped bank account field to invoice create/edit/drawer forms.
  - [x] Update invoice create/edit/drawer/quick-save/autosave paths to persist and validate the selected account.
  - [x] Update bulk last-month creation and Billings/import invoice creation to set an account.
  - [x] Update invoice preview/PDF templates to render the invoice-selected account.
  - [x] Add invoice tests for defaulting, override, cross-issuer rejection, bulk creation, and PDF context.

- [x] Add preview-safe evidence coverage
  - [x] Update smoke seed data to include multiple issuer bank accounts and a prior invoice with a non-default account.
  - [x] Add `tests/e2e/company-bank-accounts.spec.js` for company settings, invoice selection, and invoice preview evidence.
  - [x] Encode the named full-page screenshot checkpoints required by this spec.
  - [x] Keep the scenario runnable through `./scripts/e2e.sh` locally and against preview-backed review environments.

## Deployment / Rollout

- Run Django migrations during the normal deploy process.
- No feature flag is required.
- Existing companies retain their current bank information as the initial default account.
- Existing invoices should continue to render with equivalent payment information after backfill.
- Existing generated PDF files remain unchanged until regenerated.

## File-Level Changes

### Add

- `invoices/migrations/0062_*.py` or next migration — bank account model, invoice relation, and backfill.
- `tests/e2e/company-bank-accounts.spec.js` — issue-specific Playwright evidence.
- Optional `invoices/services/bank_accounts.py` — default/last-used account resolution helpers.

### Modify

- `invoices/models.py` — add issuer bank account model and invoice relation.
- `invoices/forms.py` — add bank account form/formset and invoice selector field.
- `invoices/views.py` — wire company settings, invoice flows, bulk creation, autosave, and PDF context.
- `invoices/templates/invoices/company_settings.html` — replace single account textarea with multi-account management UI.
- `invoices/templates/invoices/form_invoice.html` and `invoices/templates/invoices/partials/invoice_form_inner.html` — expose account selector.
- `invoices/templates/invoices/invoice_pdf.html` and `invoices/templates/invoices/billings_tf_eur.html` — render selected invoice account.
- `invoices/static/invoices/js/invoice_dates.js` or a new invoice form script — update suggested account when project/client changes.
- `invoices/admin.py` — expose bank accounts and invoice account relation.
- `invoices/management/commands/seed_e2e_smoke.py` — seed multiple accounts for evidence/testing.
- `invoices/tests/test_company.py` and `invoices/tests/test_invoices.py` — add targeted coverage.

### Keep

- Existing payment term, payment note, invoice totals, order-line, and payment application behavior.
- Existing company switching and issuer access-control model.
- Existing generated PDF files unless regenerated through the current app flows.

## Demo Media

Source-of-truth note: define a new issue-specific Playwright scenario for this work. Do not infer reuse from existing invoice or company settings specs.

### Scenario: company-bank-accounts-invoice-selection

#### Repo Command

`PLAYWRIGHT_VIDEO=on OPENCODE_DEMO_SCENARIO=company-bank-accounts-invoice-selection ./scripts/e2e.sh tests/e2e/company-bank-accounts.spec.js --project=chromium`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open Company information and show the Finance area with multiple bank accounts and a visible default account.
3. Add or edit a secondary bank account using safe test-visible account details, then save.
4. Open a new invoice for a client with prior invoice history and show the bank account selector using the expected suggested account.
5. Change the selected bank account and save the invoice.
6. Open the invoice preview/PDF state and show the payment information rendered from the selected invoice account.

#### Screenshot Checkpoints

- `company-bank-accounts-settings-full-page` — full-page screenshot of Company information with the multi-account Finance area and visible default account.
- `invoice-bank-account-selector-full-page` — full-page screenshot of the invoice form with the bank account selector visible.
- `invoice-selected-bank-account-preview-full-page` — full-page screenshot of the invoice preview/PDF state with selected-account payment details visible.

## Visual Validation

No existing visual path is reused implicitly. Use the same issue-specific Playwright command as Demo Media after adding the checkpoints.

### Identifier

company-bank-accounts-ui

### Capture Command

`./scripts/e2e.sh tests/e2e/company-bank-accounts.spec.js --project=chromium`

### Steps

1. Open Company information and capture the full page with the multi-account Finance area visible.
2. Open a new or editable invoice and capture the full page with the bank account selector visible.
3. Open the invoice preview/PDF state and capture the full page with selected bank account payment details visible.

### Full-Page Checkpoints

- `company-bank-accounts-settings-full-page`
- `invoice-bank-account-selector-full-page`
- `invoice-selected-bank-account-preview-full-page`

### Expected Comparisons

- Reviewers should see Company information move from one bank-account textarea to multi-account management with one default.
- Reviewers should see invoice forms gain a bank account selector without unrelated invoice layout changes.
- Reviewers should see invoice preview/PDF payment details follow the selected invoice account.
- Reviewers should not see unrelated changes to totals, order lines, payment terms, or client billing fields.

### Baseline SHA

`0badf43b8e540b4aac9e9614767385cfe4b34bc7`


## Open Questions

None.
