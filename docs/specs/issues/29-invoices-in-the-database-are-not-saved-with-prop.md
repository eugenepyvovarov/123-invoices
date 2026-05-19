# Overview

Fix invoice currency persistence so invoices store their own currency snapshot when saved, and backfill historical invoices where `invoice.currency` is currently missing. For the historical repair, use the current linked `customer.currency` as the accepted source of truth.

# Problem

Invoices can be saved with `customer` and `project` populated but `invoice.currency` left `NULL`. The UI currently masks some of this by falling back to `invoice.customer.currency`, but the database row itself remains incomplete.

This causes three practical issues:

- invoice records are not self-contained snapshots
- screens and downstream logic that read `invoice.currency` directly can show missing currency
- historical rows need corrective repair so the list/detail views stop depending on fallback behavior

The attached example shows persisted invoices where currency is absent for some rows that should have one.

# Proposed Outcome

Invoice save behavior should consistently persist currency snapshot data onto the invoice itself whenever the invoice resolves to a customer with a currency. The stored snapshot should include:

- `invoice.currency`
- `invoice.exchange_rate`
- `invoice.base_currency_total` recalculated from stored totals when enough data exists

Historical invoices with `currency IS NULL` should be backfilled from the current linked `customer.currency`, and that backfill should also populate related snapshot fields where derivation is straightforward and safe.

# Constraints / Non-Goals

- Do not add a manual currency selector to invoice create/edit flows in this issue.
- Do not redesign broader multi-currency behavior beyond invoice persistence correctness.
- Do not overwrite invoices that already have a stored `currency`.
- Do not guess currency for invoices that have no linked customer currency.
- Do not replace importer-specific explicit currency assignment with customer-derived values when a flow already sets invoice currency intentionally.
- Do not attempt to reconstruct the historically exact original currency if the customer has changed; the accepted backfill rule is to use the current `customer.currency`.

# Acceptance Criteria

## User Outcome

1. Creating an invoice for a customer with a configured currency stores that currency on the invoice record.
2. Editing an invoice through the app no longer leaves `invoice.currency` empty when the linked customer has a configured currency.
3. Previously affected invoices with a linked customer currency display a populated stored currency after the backfill runs.

## Technical Behavior

1. Invoice persistence applies one shared rule for deriving missing invoice currency snapshot data from the linked customer context.
2. The shared rule populates `currency` and `exchange_rate` when they are missing and a linked customer currency exists.
3. The shared rule recalculates `base_currency_total` from stored invoice totals and exchange rate for repaired rows where those values are available.
4. Existing invoices that already have a stored `currency` are left unchanged by the backfill.
5. Invoice flows that already provide an explicit invoice currency continue to preserve that explicit value rather than being replaced by customer-derived data.
6. Invoices with no recoverable linked customer currency remain unchanged.

## Operations / Deployment

1. The fix ships with a repository-tracked data migration or equivalent deploy-safe repair step for historical invoices.
2. The historical repair is idempotent for rows that already contain stored currency data.
3. Rollout guidance identifies that historical invoice rows with missing currency will be updated in place.

## Validation

1. Automated tests cover form-driven invoice saves persisting currency from the linked customer.
2. Automated tests cover the shared persistence path at the model or helper level so non-form save flows are protected.
3. Automated tests cover the historical backfill for repairable rows.
4. Automated tests confirm rows with no linked customer currency, and rows with already populated invoice currency, remain unchanged.

# Implementation Plan

1. Introduce a shared invoice snapshot routine close to the `Invoice` model so all save paths can use the same derivation rule.
2. Apply that routine during invoice persistence, preferably in model-level save behavior or a model-owned helper invoked from save, so create/edit flows stop depending on `InvoiceForm` alone.
3. Ensure the routine only fills missing snapshot fields and does not overwrite an explicitly assigned invoice currency.
4. Add a data migration that backfills invoices where `currency` is null and the linked customer currently has a currency.
5. Add regression coverage for form saves, model-level persistence, and the migration behavior.

# Task List

- [x] Centralize invoice currency snapshot logic
  - [x] Add an `Invoice`-owned helper or save-path routine that derives missing currency data from the linked customer.
  - [x] Populate missing `exchange_rate` from the resolved currency’s `exchange_rate_to_base`.
  - [x] Recompute `base_currency_total` from stored totals when snapshot fields are filled.
  - [x] Add unit tests for the shared snapshot behavior, including preservation of explicitly assigned invoice currency.

- [x] Apply the shared logic to invoice save flows
  - [x] Update invoice persistence so form-driven create/edit saves use the shared snapshot logic automatically.
  - [x] Verify seeded create/edit flows in `invoices.views` persist currency without extra fallback-only behavior.
  - [x] Add regression tests for form save behavior with and without a customer currency.

- [x] Backfill historical invoices with missing stored currency
  - [x] Add a data migration after the current latest migration to repair invoices with `currency IS NULL`.
  - [x] Limit the migration to rows with a linked customer whose current currency is set.
  - [x] Add migration-focused tests covering repairable rows, already-correct rows, and unrecoverable rows.

# Deployment / Rollout

- Run the new data migration as part of the normal deployment sequence.
- Expect historical invoices with missing stored currency to be updated in place using current linked `customer.currency`.
- Validate rollout by comparing counts before and after deployment for:
  - invoices with `currency IS NULL`
  - invoices with `currency IS NULL` and a linked customer currency
- No feature flag is needed; this is a data-correctness fix.
- Any invoices that still lack a recoverable customer currency after rollout should remain untouched for manual review.

# File-Level Changes

## Add

- `invoices/migrations/0056_backfill_invoice_currency.py` (final number to match migration order)

## Modify

- `invoices/models.py` to centralize invoice currency snapshot persistence
- `invoices/forms.py` only if needed to keep form save behavior aligned with the shared model logic
- `invoices/views.py` only if a small cleanup is needed around invoice seed/fallback handling after persistence is corrected
- `invoices/tests/test_invoices.py` to add regression coverage for persistence and backfill behavior

## Keep

- `invoices/management/commands/import_billings.py` behavior that already sets explicit invoice currency data during import
- existing customer currency management flows
- existing UI fallback/display helpers unless a small cleanup is warranted after persistence is fixed

# Open Questions

None.
