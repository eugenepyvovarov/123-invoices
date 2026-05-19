## Overview

Build a generic expense CSV import flow that replaces the Wise-only parser with reusable mappings, AI-assisted mapping proposals, row selection, per-user OpenAI-compatible provider settings, and read-only global mappings.

Assumption: the issue title’s “css parser” means CSV parser, because the issue body consistently describes CSV imports.

## Problem

The current import path is hard-coded around Wise CSV exports. That prevents users from importing expense exports from other banks, cards, and accounting systems with different headers, date formats, amount signs, and transaction identifiers.

The existing Wise import should be preserved during the refactor. It should become a seeded, read-only global mapping so Wise CSVs continue to work without requiring AI settings.

## Proposed Outcome

Implement a multi-step generic expense CSV import flow:

1. Users configure OpenAI-compatible import provider settings in User settings:
   - provider base URL
   - model name
   - API key as a masked/write-only secret
2. The system supports two mapping scopes:
   - read-only global mappings available to all users
   - named user mappings scoped to the user who saved them
3. The current Wise import behavior is seeded as a read-only global mapping.
4. Users upload CSV or ZIP exports from the Expenses page.
5. The system reads headers and limited sample rows, then chooses a mapping source in this order:
   - matching user-owned saved mapping
   - matching global mapping, including Wise
   - AI structured-output mapping proposal from the user’s configured provider
6. Users review and adjust the mapping before import.
7. Users can name and save a confirmed mapping for later reuse.
8. Users preview candidate rows and select only the entries that should become company expenses.
9. Only selected rows create `Expense` records for the active company.
10. Existing Wise import entry points route into the generic import flow or remain only as compatibility shims.

Recommended first cut: use AI only for mapping inference. Parsing, previewing, row selection, duplicate detection, and import creation should be deterministic from the confirmed mapping.

## Constraints / Non-Goals

- OpenAI-compatible provider credentials are stored per user through the app UI; do not rely on one deployment-wide provider secret.
- Seed Wise as a global built-in mapping, but do not build a global-mapping management UI in this issue.
- User-created mappings remain private and should take precedence over global mappings for matching CSV structures.
- Do not call the model when a matching user or global mapping is available.
- Do not call the model for every row after a mapping is confirmed.
- Do not send entire CSV files to the model by default; send headers plus limited sample rows only.
- Do not import unselected preview rows.
- Do not auto-link imported expenses to customers, projects, invoices, receipts, or accounting categories.
- Do not remove manual expense create/edit/list behavior.
- Do not expose saved API keys in templates, JSON responses, logs, screenshots, or fixtures.
- Reviewer evidence must not depend on live provider credentials; use committed fixtures and deterministic stubs.

## Acceptance Criteria

### User Outcome

1. A user can configure provider base URL, model name, and API key from User settings.
2. A user can open a generic CSV import flow from the Expenses page instead of a Wise-only flow.
3. Wise-format CSVs can still be imported through the generic flow without AI provider settings.
4. Non-Wise CSVs can receive an AI-proposed mapping when the user has provider settings configured.
5. A user can review and adjust proposed or matched mappings before importing.
6. A user can name and save a personal mapping for future uploads.
7. A future upload with the same recognizable structure suggests the user’s saved mapping before global mappings or AI inference.
8. A matching global mapping is available when no user mapping matches.
9. A user can select which preview rows should be imported.
10. Only selected rows are created as expenses for the active company.

### Technical Behavior

1. Import mappings support `global` and `user` scope.
2. The Wise global mapping is read-only, available to all users, and preserves the current Wise field mapping and default expense-row behavior.
3. Mapping lookup prefers user-owned mappings over global mappings.
4. Header signatures normalize casing, whitespace, BOMs, and compatible extra columns.
5. AI structured output is validated against actual CSV headers and supported expense fields before acceptance.
6. Provider settings are scoped to the authenticated user.
7. Saved API keys are masked/write-only; blank edit preserves the existing key, and an explicit clear action removes it.
8. Import execution uses the confirmed mapping and does not require another model call.
9. Duplicate detection is scoped to the active issuer and import source context, using a mapped transaction id when available and a stable row fingerprint otherwise.
10. Amounts are normalized to positive two-decimal expense values while preserving raw row data for traceability.
11. Provider failures, invalid structured output, missing provider settings, invalid mappings, and invalid row values produce clear in-page errors and do not create expenses.
12. Existing expense list, drawer, reporting exclusion, dashboard totals, and bulk download behavior remain intact.

### Operations / Deployment

1. Migrations create provider settings, import mappings, mapping signatures, and import preview/tracking persistence.
2. A data migration or committed seed path creates the Wise global mapping idempotently.
3. Existing Wise-imported expenses remain untouched.
4. The app deploys safely when no user has configured provider settings.
5. No live provider calls run during deployment, migrations, or tests.
6. Normal static collection and migration steps are sufficient for rollout.

### Validation

1. Django tests cover provider settings save/update/clear/masking behavior.
2. Django tests cover Wise global mapping seed behavior, read-only global mappings, user mapping precedence, mapping persistence, and mapping auto-match.
3. Django tests cover structured-output validation, row selection, duplicate handling, and selected-row import creation.
4. Django tests cover missing/invalid provider settings and provider failure behavior without live network calls.
5. Existing Wise importer tests are replaced or adapted so Wise-format CSVs are covered through the generic importer and seeded global mapping.
6. Playwright coverage exercises the preview-safe generic import flow with committed CSV fixtures and deterministic AI mapping stubs.
7. Demo and visual-validation evidence use the spec-declared Playwright command and named full-page checkpoints.

## Demo Media

Source-of-truth note: define or update issue-specific scenarios for this work. Do not implicitly reuse the existing Wise import Playwright path unless it is explicitly updated to the scenario identifiers and command below.

### Scenario: expense-csv-generic-import

#### Repo Command

`./scripts/e2e.sh tests/e2e/expense-csv-import.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open User settings and show the OpenAI-compatible expense import settings area with safe placeholder values only.
3. Save provider settings and show the saved state with the API key masked.
4. Open the Expenses page and show the generic CSV import entry point.
5. Upload a committed non-Wise CSV fixture and use a deterministic mocked/stubbed structured response to show a proposed mapping.
6. Review the proposed mapping, adjust at least one mapping control if needed, and save the mapping with a visible name.
7. Continue to the preview table and leave a mix of candidate rows selected and unselected.
8. Confirm the import and show the resulting in-place summary or redirected Expenses state.

#### Screenshot Checkpoints

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

- `expense-import-wise-global-mapping-full-page`
- `expense-import-wise-row-selection-full-page`
- `expense-import-wise-result-full-page`

## Visual Validation

No existing visual path is reused implicitly. Use the same issue-specific Playwright command as Demo Media after adding the import-flow checkpoints.

### Identifier

expense-generic-csv-import-ui

### Capture Command

`./scripts/e2e.sh tests/e2e/expense-csv-import.spec.js`

### Steps

1. Open User settings and capture the full page with OpenAI-compatible provider/model settings visible using safe placeholder values only.
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

- Reviewers should see per-user provider settings without exposure of the full saved API key.
- Reviewers should see the Wise-specific import affordance replaced by a generic expense CSV import entry point.
- Reviewers should see a mapping-review state that explains how CSV columns map into expense fields.
- Reviewers should see Wise-format uploads use a built-in global mapping instead of a separate Wise-only import UI.
- Reviewers should see row selection before expenses are created.
- Reviewers should not see unrelated layout changes to the rest of the Expenses page.

### Baseline SHA

`b6ad1a281db5ee0670144f413ce56360e481c917`


## Implementation Plan

1. Add persistence for import mappings with scope, optional owner, name, normalized header signature, mapping JSON, default row-selection rules, read-only flag, and timestamps.
2. Add import batch/preview persistence scoped to user and active issuer.
3. Seed the current Wise CSV behavior as an idempotent read-only global mapping.
4. Add per-user OpenAI-compatible provider settings with protected API key handling and masked/write-only UI behavior.
5. Replace or wrap `WiseStatementImporter` with a generic CSV import service that parses CSV/ZIP inputs, detects signatures, matches mappings, infers mappings, validates mappings, previews rows, and creates selected expenses.
6. Add an OpenAI-compatible structured-output client wrapper with a strict mapping schema and deterministic test doubles.
7. Update the Expenses import UI into upload, mapping review, save/reuse mapping, row selection, and result states.
8. Route existing Wise buttons/endpoints into the generic flow or keep a temporary compatibility shim.
9. Update Django and Playwright coverage around services, views, forms, settings, global mappings, and preview-safe evidence.

## Task List

- [x] Add import mapping persistence and Wise global seed
  - [x] Add mapping storage with scope, owner, name, normalized header signature, mapping JSON, default row-selection rules, read-only flag, and timestamps.
  - [x] Add import batch/preview storage scoped to user and active issuer.
  - [x] Seed the current Wise mapping as a read-only global mapping.
  - [x] Add migrations and model tests for ownership, global visibility, user precedence, and Wise seed idempotency.

- [x] Build generic CSV mapping and import services
  - [x] Replace or wrap the Wise-only importer with a generic CSV/ZIP parser for common encodings and delimiters.
  - [x] Add mapping lookup in user, global, then AI-inference order.
  - [x] Add structured-output mapping inference through an OpenAI-compatible client wrapper.
  - [x] Validate inferred mappings against actual headers and required expense targets.
  - [x] Normalize dates, amounts, descriptions, transaction ids, currencies, and raw row data from confirmed mappings.
  - [x] Add service tests for Wise CSVs, non-Wise CSVs, invalid mappings, duplicates, provider errors, and selected-row imports.

- [x] Update the expense import UI flow
  - [x] Rename the Expenses page import entry point from Wise-specific to generic CSV import.
  - [x] Route or remove remaining Wise import buttons on Expenses, project detail, and customer profile screens.
  - [x] Build upload, mapping review, saved/global mapping selection, row preview, and result states.
  - [x] Add client behavior for advancing between import states and preserving row selections.
  - [x] Add view/form tests for authorization, validation errors, global mapping use, saved mapping reuse, and selected-row confirmation.

- [x] Add AI provider settings UI
  - [x] Add provider base URL, model name, API key, and clear-key controls to User settings.
  - [x] Render saved credentials as masked/write-only values.
  - [x] Validate required fields before enabling AI mapping inference for unmatched CSVs.
  - [x] Add tests for saving, updating, clearing, preserving, and masking settings.

- [x] Add preview-safe Playwright evidence code
  - [x] Add non-Wise CSV fixtures, Wise CSV fixtures, and deterministic mapping fixtures.
  - [x] Add or update `tests/e2e/expense-csv-import.spec.js` using the repo-owned smoke auth flow.
  - [x] Stub or mock the AI mapping call so evidence does not require live provider credentials.
  - [x] Capture the named demo and visual-validation full-page checkpoints from the committed scenario.

## Deployment / Rollout

This rollout requires migrations and static asset updates.

1. Deploy through the normal build path with migrations enabled.
2. Run the Wise global mapping seed idempotently as part of migrations or a committed seed routine.
3. Leave existing `Expense` records untouched, including expenses previously imported from Wise.
4. Replace the Wise-only UI path with the generic import flow; keep any old Wise endpoint only as a compatibility shim if needed.
5. Users without provider configuration can still use matching global mappings such as Wise.
6. Unmatched CSVs should explain that AI mapping inference requires provider configuration.
7. Users configure their own provider credentials after deployment; no shared deployment-wide provider secret is required.
8. Smoke-check the Expenses import entry point, User settings provider form, a Wise-style import, and a non-Wise fixture-style import in preview before relying on live imports.

## File-Level Changes

### Add

- `invoices/services/expense_importer.py` — generic CSV parsing, mapping lookup/application, preview, duplicate detection, and import creation.
- `invoices/services/expense_import_ai.py` — OpenAI-compatible structured-output client wrapper.
- New migrations for import mappings, Wise global mapping seed, provider settings, and import preview/tracking persistence.
- `expenses/templates/expenses/partials/expense_import_modal.html` — generic import flow UI.
- `invoices/static/invoices/js/expense_import.js` — client behavior for mapping review and row selection.
- `invoices/tests/test_expense_importer.py` and/or focused service/view test modules.
- `tests/e2e/expense-csv-import.spec.js`.
- `tests/e2e/fixtures/expense-import/` CSV and mapping fixtures.

### Modify

- `invoices/models.py` — add import mapping and import batch/preview persistence; adjust expense import uniqueness if needed for issuer-scoped duplicate detection.
- `accounts/models.py`, `accounts/forms.py`, `accounts/views.py`, and `accounts/templates/accounts/user_settings.html` — add per-user provider settings.
- `expenses/views.py`, `expenses/urls.py`, and `expenses/templates/expenses/expenses_list.html` — add generic import endpoints and entry point.
- `invoices/templates/invoices/project_detail.html` and `invoices/templates/invoices/customer_profile.html` — route or remove Wise-specific import buttons.
- `invoices/templates/invoices/partials/wise_import_modal.html` — replace with the generic import modal or remove if no longer included.
- `invoices/static/invoices/js/wise_import.js` — replace with generic import behavior or remove.
- `invoices/views.py` and `invoices/urls.py` — route `payments_import_wise` to the generic importer or retire it after compatibility is covered.
- `invoices/services/wise_importer.py` — remove, rename, or keep only as a compatibility adapter around the generic importer.
- Existing Wise Django and Playwright tests — adapt to the generic import flow and Wise global mapping.
- `requirements.txt` — add a provider/client or encryption dependency only if existing utilities are insufficient.

### Keep

- Existing manual `Expense` create/edit/list behavior.
- Existing expense reporting exclusion behavior.
- Existing dashboard aggregation behavior.
- Existing bulk expense download behavior.
- Existing Playwright smoke auth helpers and preview-backed evidence infrastructure.

## Open Questions

None.
