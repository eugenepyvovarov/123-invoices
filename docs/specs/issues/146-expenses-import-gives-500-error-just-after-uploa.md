## Overview

Fix the generic expense statement import flow so the approved attached CaixaBank CSV uploads to manual mapping review instead of crashing or blocking before the user can understand the file format. The user should be able to save that mapping and have future same-header uploads reuse it automatically.

## Problem

The upload flow currently depends on resolving a saved/global/AI mapping before the parsed statement is usable. For a parseable but previously unknown file, that can surface as a 500 or a blocking post-upload error, preventing the user from seeing detected headers, manually mapping columns, saving the mapping, or reusing it later.

## Proposed Outcome

1. The attached `Item;Date;Amount;Balance` CSV reaches manual mapping review when no selected, user, global, or usable AI mapping exists.
2. Manual mapping review shows detected headers with blank/default selections.
3. Users can map required fields, continue to row selection, and import only after confirmation.
4. Users can save a named user mapping from the review step.
5. Future same-header uploads automatically reuse the saved user mapping without requiring AI.
6. AI mapping remains optional; missing settings, provider failures, and invalid AI output fall back to manual mapping review.

## Constraints / Non-Goals

- Use the same attached CSV content as the committed issue-146 regression fixture; the latest issue comment explicitly approves using the file rather than a synthetic substitute.
- Do not commit any additional bank statement data beyond the approved issue fixture, and keep generated uploads, screenshots, videos, and databases out of git.
- Do not add a CaixaBank-specific importer unless the attached file exposes a generic parser bug.
- Do not require live AI provider credentials for upload, mapping, tests, preview, or reviewer evidence.
- Do not create expenses until the user confirms selected preview rows.
- Do not build a global mapping management UI.
- Do not change unrelated manual expense, dashboard, invoice, or incoming-invoice behavior.
- Keep existing expense import route names compatible.
- Keep saved mappings private per user, matching the existing `ImportMapping` user/global scope model.

## Acceptance Criteria

### User Outcome

1. Uploading the committed issue-146 CSV with no matching mapping and no AI credentials renders manual mapping review instead of a 500 or blocking error.
2. The review page exposes the detected `Item`, `Date`, `Amount`, and `Balance` headers for selection.
3. A user can map `Date` and `Amount`, optionally map `Item` as the description, continue to row selection, and import selected rows.
4. No expenses are created before the row-selection confirmation step.
5. A user can save the reviewed mapping with a name.
6. A later upload with the same header structure automatically applies the saved user mapping.
7. Corrupt or unparseable uploads still show a controlled in-page error and create no expenses.

### Technical Behavior

1. The semicolon CSV with localized `+/-` amount values, `EUR` suffixes, and `dd/mm/yyyy` dates parses through the generic statement parser.
2. Upload handling persists parsed headers and raw rows before mapping inference is required to succeed.
3. Parsed-but-unmapped uploads use `ImportBatch.STATUS_UPLOADED` or an equivalent existing state until review submission creates preview rows.
4. Mapping resolution order remains selected mapping, user mapping, global mapping, AI prefill when available, then manual fallback.
5. Missing AI settings, `ExpenseImportAIError`, provider exceptions, invalid AI output, and invalid inferred mappings do not produce uncaught exceptions.
6. Explicitly selected mapping mismatches remain controlled validation errors.
7. Review submission validates required mapping fields before preview rows are generated.
8. Saved mapping reuse does not call AI for matching future uploads.
9. Import batches, preview rows, and created expenses remain scoped to the authenticated user and active issuer.

### Operations / Deployment

1. No database migration is expected because existing `ImportBatch`, `ImportMapping`, `ImportPreviewRow`, and metadata fields can represent the fallback flow.
2. Existing saved mappings and imported expenses remain valid.
3. Deployment does not require AI credentials or private external attachment access.
4. Normal build, migration, static collection, and deployment steps remain sufficient.

### Validation

1. Django tests cover the approved issue-146 CSV reaching manual mapping review without AI settings.
2. Django tests cover AI provider failure and invalid inferred mapping falling back to manual mapping review without creating expenses.
3. Django tests cover saving a mapping from manual review and reusing it on a future same-header upload.
4. Django tests cover corrupt/unparseable uploads returning controlled errors.
5. Existing Wise/global mapping, selected mapping, AI-prefill, row selection, duplicate detection, CSV, XLS, XLSX, and ZIP import tests continue to pass.
6. Playwright reviewer evidence covers manual mapping fallback and saved mapping reuse with the committed issue-146 fixture.

## Implementation Plan

1. Trace `expenses.views.expense_csv_import`, `expense_csv_import_review`, and `GenericExpenseImporter.resolve_mapping` for parsed statements with no matching mapping and for AI/provider exceptions.
2. Split parsing and batch persistence from mapping resolution so parsed headers/raw rows can be stored even when no mapping is available.
3. Add or reuse an uploaded/manual-review batch path that stores normalized header signature, raw headers, source filename, and raw rows without creating preview rows.
4. Update automatic mapping resolution so selected/user/global mappings still prefill review, AI remains optional, and all unusable automatic mapping paths fall back to manual review.
5. Render existing mapping review controls with detected headers and empty/default field selections for manual fallback.
6. On review submission, validate the selected mapping, save a named user mapping when requested, generate preview rows from stored raw rows, and preserve existing import confirmation behavior.
7. Add focused Django tests and preview-safe Playwright evidence using the committed issue-146 CSV fixture.

## Task List

- [ ] Add manual mapping fallback after upload
  - [ ] Split upload parsing from mapping resolution so parsed headers/raw rows can be stored before mapping success.
  - [ ] Add or reuse importer/view helpers to create an uploaded manual-review batch without preview rows.
  - [ ] Return manual mapping review when no selected, user, global, or AI mapping is usable.
  - [ ] Convert AI inference/provider exceptions and invalid AI output into controlled manual-fallback feedback.
  - [ ] Add focused tests for no-mapping/no-AI, AI failure, and invalid AI mapping upload paths.

- [ ] Complete mapping review, save, and reuse behavior
  - [ ] Render blank manual mapping controls using parsed upload headers.
  - [ ] Allow the review endpoint to accept manual-review batches and validate required fields.
  - [ ] Generate preview rows from stored raw rows after valid manual mapping submission.
  - [ ] Save named user mappings with the batch’s normalized header signature.
  - [ ] Reuse saved user mappings automatically on future same-header uploads without AI calls.

- [ ] Add approved fixture and reviewer evidence automation
  - [ ] Commit the approved issue-146 CSV fixture under the existing expense-import fixture area.
  - [ ] Add parser/view/import regression coverage that uses the committed fixture.
  - [ ] Extend `tests/e2e/expense-statement-import.spec.js` for manual fallback, mapping save, and saved mapping reuse.
  - [ ] Update `scripts/demo-evidence.sh` with the declared demo scenario identifier.
  - [ ] Update `scripts/visual-validation.sh` with the declared visual-validation identifier and baseline/current target handling.

## Deployment / Rollout

1. Deploy through the normal application pipeline.
2. Run migrations as usual; no schema migration is expected unless implementation discovers a concrete schema gap.
3. Existing mappings continue to work immediately after deploy.
4. After rollout, smoke-check by uploading the issue-146 CSV shape, saving a mapping, and re-uploading the same-header statement.
5. No AI credential or external attachment retrieval is required for production deployment.

## File-Level Changes

### Add

- `tests/e2e/fixtures/expense-import/issue-146-caixabank-now.csv` — committed copy of the approved attached CSV fixture.

### Modify

- `expenses/views.py` — upload/review flow, AI error handling, manual fallback context, and mapping save/reuse behavior.
- `expenses/templates/expenses/expense_import.html` — manual mapping fallback feedback and review-state copy.
- `invoices/services/expense_importer.py` — mapping resolution, batch creation helpers, preview generation, and fallback behavior.
- `expenses/tests/test_import_views.py` — view tests for fallback, save, reuse, and controlled errors.
- `invoices/tests/test_expense_importer.py` — parser/importer regression coverage for the issue fixture and fallback behavior.
- `tests/e2e/expense-statement-import.spec.js` — reviewer evidence for manual mapping and saved mapping reuse.
- `scripts/demo-evidence.sh` — add `expense-import-manual-mapping` scenario.
- `scripts/visual-validation.sh` — add `expense-import-manual-mapping-fallback` capture identifier.

### Keep

- Existing `ImportMapping`, `ImportBatch`, and `ImportPreviewRow` schema unless a concrete gap is found.
- Existing Wise global mapping seed and mapping precedence.
- Existing CSV, XLS, XLSX, and ZIP parsing support.
- Existing expense list, manual expense, dashboard, and incoming-invoice behavior.
- Managed workflow files unchanged.

## Demo Media

### Scenario: expense-import-manual-mapping

#### Repo Command

./scripts/demo-evidence.sh expense-import-manual-mapping

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned preview user flow and open the expense import page.
2. Upload the committed issue-146 CSV fixture with no pre-seeded matching mapping and no live AI credentials.
3. Leave the UI in manual mapping review with parsed headers available for selection.
4. Select the required mapping fields, provide a mapping name, and continue to row selection.
5. Return to import upload, upload another same-header fixture, and leave the UI showing the saved mapping applied for reuse.

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
2. In baseline mode, upload the issue-146 CSV with no matching mapping and no live AI credentials, then capture the stable pre-existing blocking response or upload-page fallback without requiring PR-only manual mapping controls.
3. In baseline mode, use the same stable fallback state for the saved-mapping reuse checkpoint because the baseline cannot save and reuse the new manual mapping.
4. In current mode, upload the issue-146 CSV and capture the manual mapping review state.
5. In current mode, save the mapping, upload a same-header statement again, and capture the saved-mapping reuse state.

### Full-Page Checkpoints

- expense-import-unmatched-mapping-full-page: full-page screenshot of the unmatched upload state
- expense-import-saved-mapping-reuse-full-page: full-page screenshot of the same-header upload after saving a mapping

### Expected Comparisons

- The unmatched-upload comparison should show the flow changing from a blocking/error state to an editable manual mapping review state.
- The saved-mapping reuse comparison should show the current flow applying the saved mapping where baseline can only show the fallback state.
- Reviewers should not see unrelated layout changes to the Expenses list or manual expense controls.

## Open Questions

None.
