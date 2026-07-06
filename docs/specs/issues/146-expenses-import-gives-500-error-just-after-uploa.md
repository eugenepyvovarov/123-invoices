## Overview

Fix the expense statement import flow so a parseable but previously unknown upload does not crash or stop at mapping detection. Users should be able to manually map the uploaded file’s columns, save that mapping, and have the same file structure detected on future uploads.

## Problem

The current upload path can fail or return a blocking error after parsing when no saved/global mapping is available or AI mapping inference fails. That prevents the user from inspecting the detected headers, manually mapping the file, saving the mapping, or reusing it later.

## Proposed Outcome

1. Parseable unknown expense statement uploads reach manual mapping review instead of a 500 or blocking post-upload error.
2. Manual mapping review starts with detected headers and blank field selections when no mapping is found.
3. Users can select required columns, continue to row selection, and optionally save the mapping under a user-provided name.
4. Future uploads with the same normalized header signature reuse the saved user mapping without requiring AI.
5. AI mapping remains an optional prefill source, but missing settings, provider errors, and invalid AI output fall back to manual mapping review.

## Constraints / Non-Goals

- Use the attached statement as the source for a committed sanitized regression fixture, preserving the relevant file format/header/table shape while removing or replacing real values.
- Do not commit the raw attached statement or real customer/account data.
- Do not add a bank-specific importer unless a parser bug must be fixed generically for the attached file shape.
- Do not require live AI provider credentials for upload, mapping, tests, preview, or reviewer evidence.
- Do not create expenses until the user confirms selected preview rows.
- Do not build a global mapping management UI in this issue.
- Do not change unrelated manual expense, dashboard, invoice, or incoming-invoice behavior.
- Keep existing expense import route names compatible.
- Assumption: saved mappings remain private per user, matching the existing `ImportMapping` user/global scope model.

## Acceptance Criteria

### User Outcome

1. A user can upload the sanitized attached statement fixture with no matching saved/global mapping and see a mapping review page instead of a 500.
2. A user can manually map required fields, continue to row selection, and import selected rows.
3. A user can save the reviewed mapping with a name.
4. A later upload with the same header structure automatically applies the saved user mapping.
5. Corrupt or unparseable files still show a controlled in-page error and create no expenses.

### Technical Behavior

1. Upload handling persists parsed headers and raw rows before mapping inference is required to succeed.
2. Manual fallback batches retain normalized header signatures and raw rows needed for review, save, preview generation, and reuse.
3. Mapping resolution order remains selected mapping, user mapping, global mapping, AI prefill when available, then manual fallback.
4. Missing AI settings, `ExpenseImportAIError`, provider exceptions, invalid AI output, and invalid inferred mappings do not produce uncaught exceptions.
5. Review submission validates required mapping fields before preview rows are generated.
6. Saved mapping reuse does not call AI for matching future uploads.
7. Import batches, preview rows, and created expenses remain scoped to the authenticated user and active issuer.

### Operations / Deployment

1. No database migration is expected because existing `ImportBatch`, `ImportMapping`, and metadata fields can represent uploaded/manual review state.
2. Existing saved mappings and imported expenses remain valid.
3. Deployment does not require AI credentials or private attached files.
4. Normal build, migration, and static collection steps remain sufficient.

### Validation

1. Django tests cover unmatched parseable uploads reaching manual mapping review without AI settings.
2. Django tests cover AI provider failure falling back to manual mapping review without creating expenses.
3. Django tests cover saving a mapping from manual review and reusing it on a future same-header upload.
4. Django tests cover corrupt/unparseable uploads returning controlled errors.
5. Existing Wise/global mapping, selected mapping, AI-prefill, row selection, duplicate detection, CSV, XLS, XLSX, and ZIP import tests continue to pass.
6. Playwright reviewer evidence covers manual mapping fallback and saved mapping reuse with the sanitized attached-statement fixture.

## Implementation Plan

1. Trace the post-upload flow in `expenses.views.expense_csv_import` and `GenericExpenseImporter.resolve_mapping` for parsed statements with no matching mapping and for AI/provider exceptions.
2. Split parsing and batch persistence from mapping resolution so a parsed upload can create an `ImportBatch` with raw headers/raw rows even when no mapping is available.
3. Represent parsed-but-unmapped uploads with an existing batch state such as `ImportBatch.STATUS_UPLOADED`, then move the batch to mapped/preview state after valid manual review submission.
4. Render existing mapping review controls with detected headers and empty/default field selections when manual fallback is used.
5. Catch AI inference/provider failures and carry non-blocking warning context into manual mapping review instead of raising through the view.
6. On review submission, validate the selected mapping, save a named user mapping when requested, generate preview rows from stored raw rows, and preserve existing import confirmation behavior.
7. Add focused Django tests and preview-safe Playwright evidence using a sanitized derivative of the attached statement.

## Task List

- [ ] Add manual mapping fallback after upload
  - [ ] Split upload parsing from mapping resolution so parsed headers/raw rows can be stored when no mapping exists.
  - [ ] Add or reuse importer helpers to create an uploaded/manual-review batch without preview rows.
  - [ ] Return manual mapping review when no selected, user, global, or AI mapping is usable.
  - [ ] Convert AI inference/provider exceptions and invalid AI output into controlled manual-fallback feedback.
  - [ ] Add service and view tests for no-mapping/no-AI and AI-failure upload paths.

- [ ] Update mapping review, save, and reuse behavior
  - [ ] Render blank manual mapping controls using parsed upload headers.
  - [ ] Allow the review endpoint to accept the manual-review batch state and validate required fields.
  - [ ] Generate preview rows from stored raw rows after a valid manual mapping submission.
  - [ ] Save named user mappings with the batch’s normalized header signature.
  - [ ] Reuse saved user mappings automatically on future same-header uploads without AI calls.

- [ ] Add issue-specific fixture and evidence automation
  - [ ] Add a sanitized regression fixture derived from the attached statement with real values removed.
  - [ ] Extend `tests/e2e/expense-statement-import.spec.js` for manual fallback and saved mapping reuse.
  - [ ] Update `scripts/demo-evidence.sh` with the declared demo scenario identifier.
  - [ ] Update `scripts/visual-validation.sh` with the declared visual-validation identifier and baseline/current target handling.
  - [ ] Keep generated screenshots, videos, databases, and raw uploads out of git.

## Deployment / Rollout

1. Deploy through the normal application pipeline.
2. Run migrations as usual; no schema migration is expected unless implementation discovers a concrete schema gap.
3. Existing mappings continue to work immediately after deploy.
4. After rollout, smoke-check by uploading the sanitized attached-statement shape, saving a mapping, and re-uploading a same-header statement.
5. No private attached file or AI credential is required in production deployment automation.

## File-Level Changes

### Add

- `tests/e2e/fixtures/expense-import/issue-146-unmatched-statement.*` — sanitized fixture derived from the attached statement, preserving import-relevant format/header/table shape.
- New Django tests in `expenses/tests/test_import_views.py` and/or `invoices/tests/` for manual fallback, AI failure fallback, mapping save, and mapping reuse.

### Modify

- `expenses/views.py` — upload/review flow, AI error handling, manual fallback context, and mapping save/reuse behavior.
- `expenses/templates/expenses/expense_import.html` — manual mapping fallback feedback and review-state copy.
- `invoices/services/expense_importer.py` — mapping resolution, batch creation helpers, and fallback behavior.
- `tests/e2e/expense-statement-import.spec.js` — reviewer evidence for manual mapping and saved mapping reuse.
- `scripts/demo-evidence.sh` — add `expense-import-manual-mapping` scenario.
- `scripts/visual-validation.sh` — add `expense-import-manual-mapping-fallback` capture identifier.

### Keep

- Existing `ImportMapping`, `ImportBatch`, and `ImportPreviewRow` schema unless a concrete gap is found.
- Existing Wise global mapping seed and mapping precedence.
- Existing CSV, XLS, XLSX, and ZIP parsing support.
- Existing expense list, manual expense, dashboard, and incoming-invoice behavior.

## Demo Media

### Scenario: expense-import-manual-mapping

#### Repo Command

./scripts/demo-evidence.sh expense-import-manual-mapping

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned preview user flow and open the expense import page.
2. Upload the committed sanitized fixture derived from the attached statement with no pre-seeded matching mapping and no live AI credentials.
3. Leave the UI in manual mapping review with parsed headers available for selection.
4. Select the required mapping fields, provide a mapping name, and continue to row selection.
5. Return to import upload, upload another same-header sanitized statement, and leave the UI showing the saved mapping applied for reuse.

#### Screenshot Checkpoints

- expense-import-manual-mapping-review: full-page screenshot of the manual mapping review state after upload
- expense-import-manual-row-selection: full-page screenshot of parsed rows after the manual mapping is submitted
- expense-import-saved-mapping-reuse: full-page screenshot of the later same-header upload using the saved mapping

## Visual Validation

### Identifier

expense-import-manual-mapping-fallback

### Capture Command

./scripts/visual-validation.sh expense-import-manual-mapping-fallback

### Steps

1. Open the expense import page with a preview-safe user/session.
2. In baseline mode, capture the stable pre-existing unmatched-upload response or upload-page fallback without requiring PR-only manual mapping controls.
3. In current mode, upload the sanitized attached-statement fixture and capture the manual mapping review state.
4. In current mode, save the mapping, upload a same-header statement again, and capture the saved-mapping reuse state.

### Full-Page Checkpoints

- expense-import-unmatched-mapping-full-page: full-page screenshot of the unmatched upload state
- expense-import-saved-mapping-reuse-full-page: full-page screenshot of the same-header upload after saving a mapping

### Expected Comparisons

- The unmatched-upload comparison should show the flow changing from a blocking/error state to an editable manual mapping review state.
- The saved-mapping reuse current capture should show a same-header upload using the saved mapping instead of requiring remapping.
- Reviewers should not see unrelated layout changes to the Expenses list or manual expense controls.

## Open Questions

None.
