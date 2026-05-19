# Overview

Build a generic expense CSV import flow that replaces the Wise-only parser with AI-assisted mapping, saved user mappings, row selection, per-user OpenAI-compatible provider settings, and read-only global mappings.

Assumption: the issue title’s “css parser” refers to CSV parsing, because the issue body consistently describes CSV imports.

# Problem

The current import path is hard-coded around Wise CSV exports. That blocks imports from other banks, cards, and accounting exports with different headers, delimiters, date formats, amount signs, and transaction identifiers.

The current Wise import should not disappear during this refactor. It should become a built-in global mapping so Wise CSVs keep working while the system gains support for user-created mappings and AI-assisted mapping proposals.

# Proposed Outcome

Replace the Wise-specific import with a generic multi-step expense CSV import:

1. Users configure OpenAI-compatible provider settings in User settings:
   - provider base URL
   - model name
   - API key as a masked/write-only secret
2. The system stores reusable import mappings with two scopes:
   - read-only global mappings available to all users
   - named user mappings scoped only to the user who created them
3. Seed the current Wise CSV behavior as a read-only global mapping, including current field mappings and default row-selection rules for Wise expense-like rows.
4. Users open a generic expense CSV import flow from the Expenses page.
5. Users upload CSV or ZIP files.
6. The system reads headers and limited sample rows, then chooses the mapping source in this order:
   - matching user-owned saved mapping
   - matching global mapping, including the seeded Wise mapping
   - AI structured-output mapping proposal from the user’s configured provider
7. Users review and adjust mappings for expense fields:
   - paid date
   - amount
   - description / memo
   - external transaction id when available
   - currency when available
   - direction/sign handling when available
8. Users can name and save the confirmed mapping to their own account.
9. Users preview candidate rows and select only the rows that should become company expenses.
10. Only selected rows create `Expense` records for the active company.
11. Existing Wise import buttons or endpoints route into the generic flow rather than maintaining a separate Wise-only parser.

Recommended first cut: use AI only for mapping inference; parse, preview, select, deduplicate, and import rows deterministically from the confirmed mapping.

# Constraints / Non-Goals

- OpenAI-compatible provider credentials are stored per user through the app UI; do not rely on one deployment-wide provider secret.
- Seed Wise as a global built-in mapping, but do not build a full global-mapping management UI in this issue.
- User-created mappings remain private; do not share one user’s mapping with other users.
- Do not call the model when a matching user or global mapping is available.
- Do not call the model for every row once a mapping is confirmed.
- Do not send entire CSV files to the model by default; send headers plus a limited sample sufficient for mapping inference.
- Do not import unselected preview rows.
- Do not auto-link imported expenses to customers, projects, invoices, receipts, or accounting categories.
- Do not remove manual expense creation/editing.
- Do not expose saved API keys in templates, JSON responses, logs, screenshots, or test fixtures.
- Do not make reviewer evidence depend on real provider credentials; Playwright evidence must use committed fixtures and deterministic mocked/stubbed mapping responses.

# Acceptance Criteria

## User Outcome

1. A user can configure OpenAI-compatible provider base URL, model name, and API key from User settings.
2. A user can open a generic CSV import flow from the Expenses page instead of a Wise-only import flow.
3. A Wise-format CSV can still be imported through the generic flow without requiring AI provider settings.
4. A non-Wise CSV can receive an AI-proposed mapping when the user has provider settings configured.
5. A user can adjust the proposed or matched mapping before importing.
6. A user can name and save a personal mapping for later reuse.
7. A future upload with the same recognizable CSV structure automatically suggests the user’s saved mapping before global mappings or AI inference.
8. A matching global mapping is available as a fallback when no user mapping matches.
9. A user can select which preview rows should be imported.
10. Only selected rows are created as expenses for the active company.

## Technical Behavior

1. Import mappings support `global` and `user` scope.
2. The seeded Wise global mapping is read-only, available to all users, and preserves the current Wise field mapping and default expense-row behavior.
3. Mapping lookup prefers user-owned mappings over global mappings when both match the uploaded CSV structure.
4. Header signatures normalize casing, whitespace, BOMs, and column order; compatible extra columns should not break a known mapping.
5. AI structured output is validated against actual CSV headers and supported target fields before it can be accepted.
6. Provider settings are scoped to the authenticated user and are used only for that user’s import mapping requests.
7. Saved API keys are write-only/masked in the UI; leaving the key field blank on edit preserves the existing key, and an explicit clear action removes it.
8. Import execution uses the confirmed mapping deterministically and does not require another model call.
9. Duplicate detection is scoped to the active issuer and import source context, using a mapped transaction id when available and a stable row fingerprint otherwise.
10. Amounts are normalized to positive expense values while preserving raw row data for traceability.
11. Provider failures, invalid structured output, missing provider settings, invalid mappings, and invalid row values produce clear in-page errors and do not create expenses.
12. Existing manual expense list, drawer, reporting exclusion, dashboard totals, and bulk-download behavior remain intact.

## Operations / Deployment

1. Database migrations create the required provider settings, import mappings, mapping signatures, and import preview/tracking persistence.
2. A data migration or committed seed path creates the Wise global mapping idempotently.
3. Existing Wise-imported expenses remain untouched.
4. The app deploys safely when no user has configured provider settings; Wise/global matched imports still work, and unmatched CSVs explain that AI configuration is required for automatic mapping inference.
5. No live provider calls run during deployment, migrations, or test setup.
6. Normal static collection and migration steps are sufficient for rollout.

## Validation

1. Django tests cover provider settings save/update/clear/masking behavior.
2. Django tests cover global Wise mapping seed behavior, read-only global mappings, user mapping precedence, mapping persistence, and mapping auto-match.
3. Django tests cover structured-output validation, row selection, duplicate handling, and selected-row import creation.
4. Django tests cover missing/invalid provider settings and provider failure behavior without making live network calls.
5. Existing Wise importer tests are replaced or adapted so Wise-format CSVs are covered through the generic importer and seeded global mapping.
6. Playwright coverage exercises the preview-safe generic import flow with committed CSV fixtures and deterministic AI mapping stubs.
7. Demo and visual-validation evidence use the spec-declared Playwright command and named full-page checkpoints.

# Demo Media

Source-of-truth note: define or update issue-specific scenarios for this work. Do not implicitly reuse the existing Wise import Playwright path unless it is explicitly updated to the scenario identifiers and command below.

### Scenario: expense-csv-generic-import

#### Repo Command

`./scripts/e2e.sh tests/e2e/expense-csv-import.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open User settings and show the OpenAI-compatible expense import settings area with safe placeholder values only.
3. Save provider settings and show the saved state with the API key masked rather than rendered in full.
4. Open the Expenses page and show the generic CSV import entry point.
5. Upload a committed non-Wise CSV fixture and use a deterministic mocked/stubbed structured response to show a proposed mapping.
6. Review the proposed mapping, adjust at least one mapping control if needed, and save the mapping with a visible name.
7. Continue to the preview table and leave a mix of candidate rows selected and unselected.
8. Confirm the import and show the resulting in-place summary or redirected Expenses state.

#### Screenshot Checkpoints

All checkpoints should be full-page screenshots because the important reviewer-visible changes are full-page or drawer/modal states.

- `expense-ai-settings-full-page`
- `expense-import-entry-full-page`
- `expense-import-mapping-review-full-page`
- `expense-import-row-selection-full-page`
- `expense-import-result-full-page`

### Scenario: expense-csv-wise-global-mapping

#### Repo Command

`./scripts/e2e.sh tests/e2e/expense-csv-import.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open the Expenses page and show the generic CSV import entry point.
3. Upload a committed Wise-format CSV fixture without relying on live provider credentials.
4. Show the mapping review state using the built-in global Wise mapping as the visible mapping source.
5. Continue to row selection and show the preview state using the Wise mapping’s default expense-row selection behavior.
6. Confirm the import and show the resulting in-place summary or redirected Expenses state.

#### Screenshot Checkpoints

All checkpoints should be full-page screenshots because the important reviewer-visible changes are full-page or drawer/modal states.

- `expense-import-wise-global-mapping-full-page`
- `expense-import-wise-row-selection-full-page`
- `expense-import-wise-result-full-page`

# Visual Validation

No existing visual path is reused implicitly. Use the same issue-specific Playwright command as Demo Media after adding the import flow checkpoints.

### Identifier

expense-generic-csv-import-ui

### Capture Command

`./scripts/e2e.sh tests/e2e/expense-csv-import.spec.js`

### Steps

1. Open User settings and capture the full page with the OpenAI-compatible provider/model settings visible using safe placeholder values only.
2. Open the Expenses page and capture the full page showing the generic import entry point.
3. Open the import flow after a non-Wise fixture upload and capture the full page with the mapping review state visible.
4. Open the import flow after a Wise fixture upload and capture the full page with the built-in global mapping state visible.
5. Continue to row selection and capture the full page with the preview table visible.
6. Confirm the import and capture the full page showing the resulting summary or Expenses state.

### Full-Page Checkpoints

- `expense-ai-settings-full-page`
- `expense-import-entry-full-page`
- `expense-import-mapping-review-full-page`
- `expense-import-wise-global-mapping-full-page`
- `expense-import-row-selection-full-page`
- `expense-import-result-full-page`

### Expected Comparisons

- Reviewers should see per-user OpenAI-compatible provider settings without exposure of the full saved API key.
- Reviewers should see the Wise-specific import affordance replaced by a generic expense CSV import entry point.
- Reviewers should see a mapping-review state that explains how CSV columns map into expense fields.
- Reviewers should see Wise-format uploads use a built-in global mapping instead of a separate Wise-only import UI.
- Reviewers should see a row-selection preview before expenses are created.
- Reviewers should not see unrelated layout changes to the rest of the Expenses page.

# Implementation Plan

1. Add persistence for import mappings with `global` and `user` scope, normalized header signatures, mapping JSON, default row-selection rules, and timestamps.
2. Add an idempotent migration or seed path for the current Wise CSV mapping as a read-only global mapping.
3. Add per-user OpenAI-compatible provider settings with protected API key storage and masked/write-only UI behavior.
4. Replace or wrap `WiseStatementImporter` with a generic expense CSV import service that can parse CSV/ZIP inputs, detect signatures, match mappings, infer mappings, validate mappings, preview rows, and create selected expenses.
5. Add an OpenAI-compatible structured-output client wrapper with a strict schema for mapping proposals and deterministic test doubles.
6. Update the Expenses import UI into a multi-step generic flow: upload, mapping review, save/reuse mapping, row selection, and import result.
7. Route existing Wise import buttons/endpoints into the generic flow or remove them where redundant.
8. Update Django tests around services, views, forms, settings, global mappings, and import persistence.
9. Add Playwright fixture data and issue-specific preview-safe evidence scenarios.

# Task List

- [ ] Add import mapping persistence and Wise global seed
  - [ ] Add mapping storage with scope, optional owner, name, normalized header signature, mapping JSON, default row-selection rules, read-only flag, and timestamps.
  - [ ] Add import batch/preview storage scoped to user and active issuer for parsed candidate rows awaiting confirmation.
  - [ ] Seed the current Wise mapping as a read-only global mapping with current field mappings and default expense-row behavior.
  - [ ] Add migrations and model tests for mapping ownership, global visibility, user precedence, and Wise seed idempotency.

- [ ] Build generic CSV mapping and import services
  - [ ] Replace or wrap the Wise-only importer with a generic CSV/ZIP parser that handles common encodings and delimiters.
  - [ ] Add header-signature matching for user mappings first, then global mappings, then AI inference.
  - [ ] Add structured-output mapping inference through an OpenAI-compatible client wrapper using the current user’s settings.
  - [ ] Validate inferred mappings against actual headers and required expense targets.
  - [ ] Normalize dates, amounts, descriptions, transaction ids, currencies, and raw row data from confirmed mappings.
  - [ ] Add service tests for Wise-format CSV, non-Wise CSV, invalid mappings, duplicates, provider errors, and selected-row imports.

- [ ] Update the expense import UI flow
  - [ ] Rename the Expenses page import entry point from Wise-specific to generic CSV import.
  - [ ] Route or remove remaining Wise import buttons in Expenses, project detail, and customer profile screens.
  - [ ] Build upload, mapping review, saved/global mapping selection, row preview, and result states.
  - [ ] Add client-side behavior for advancing between import states and preserving row selections.
  - [ ] Add view/form tests for authorization, validation errors, global mapping use, saved mapping reuse, and selected-row confirmation.

- [ ] Add AI provider settings UI
  - [ ] Add provider base URL, model name, API key, and clear-key controls to User settings.
  - [ ] Render saved credentials as masked/write-only values and never include the full key in responses.
  - [ ] Validate required fields before enabling AI mapping inference for unmatched CSVs.
  - [ ] Add tests for saving, updating, clearing, preserving, and masking settings.

- [ ] Add preview-safe Playwright evidence code
  - [ ] Add non-Wise CSV fixtures, Wise CSV fixtures, and deterministic mapping fixtures for the import scenarios.
  - [ ] Add or update `tests/e2e/expense-csv-import.spec.js` using the repo-owned smoke auth flow.
  - [ ] Stub or mock the AI mapping call so evidence does not require live provider credentials.
  - [ ] Capture the named demo and visual-validation full-page checkpoints from the committed scenario.

# Deployment / Rollout

This rollout requires migrations and static asset updates.

1. Deploy through the normal build path with migrations enabled.
2. Run the Wise global mapping seed idempotently as part of migrations or a committed seed routine.
3. Leave existing `Expense` records untouched, including expenses previously imported from Wise.
4. Replace the Wise-only UI path with the generic import flow; keep any old internal Wise endpoint as a compatibility shim only if needed during transition.
5. Users without provider configuration can still use matching global mappings such as Wise; unmatched CSVs should explain that AI mapping inference needs provider configuration.
6. Users configure their own OpenAI-compatible credentials after deployment; no shared deployment-wide provider secret is required.
7. After deployment, smoke-check the Expenses import entry point, User settings provider form, a Wise fixture-style import, and a non-Wise fixture-style import in a non-production or preview environment before relying on it for live imports.

# File-Level Changes

## Add

- `invoices/services/expense_importer.py` — generic CSV parsing, mapping lookup/application, preview, duplicate detection, and import creation.
- `invoices/services/expense_import_ai.py` — OpenAI-compatible structured-output client wrapper.
- `expenses/templates/expenses/partials/expense_import_modal.html` — generic import flow UI.
- `invoices/static/invoices/js/expense_import.js` — client behavior for mapping review and row selection.
- New migrations for import mappings, Wise global mapping seed, provider settings, and import preview/tracking persistence.
- `invoices/tests/test_expense_importer.py` and/or focused service/view test modules.
- `tests/e2e/expense-csv-import.spec.js`.
- `tests/e2e/fixtures/expense-import/` CSV and mapping fixtures.

## Modify

- `invoices/models.py` — add import mapping, import batch/preview, and duplicate-tracking persistence; adjust expense import uniqueness if needed for issuer-scoped duplicate detection.
- `accounts/models.py`, `accounts/forms.py`, `accounts/views.py`, and `accounts/templates/accounts/user_settings.html` — add per-user provider settings UI and handling.
- `expenses/views.py` and `expenses/urls.py` — add generic import endpoints under the Expenses area.
- `expenses/templates/expenses/expenses_list.html` — update import entry point and include the new import partial/script.
- `invoices/views.py` and `invoices/urls.py` — remove or route the Wise-only import endpoint to the generic importer.
- `invoices/templates/invoices/project_detail.html` and `invoices/templates/invoices/customer_profile.html` — remove or route Wise-specific import buttons if retained.
- `invoices/services/wise_importer.py` — remove, rename, or keep only as a compatibility adapter around the generic importer.
- Existing Wise import Django and Playwright tests — adapt coverage to the generic import flow and global Wise mapping.
- `requirements.txt` — add a provider/client or encryption dependency only if the implementation does not use existing project utilities or a small internal HTTP wrapper.

## Keep

- Existing manual `Expense` create/edit/list behavior.
- Existing expense reporting exclusion behavior.
- Existing dashboard aggregation behavior.
- Existing bulk expense download behavior.
- Existing Playwright smoke auth helpers and preview-backed evidence infrastructure.

# Open Questions

None.
