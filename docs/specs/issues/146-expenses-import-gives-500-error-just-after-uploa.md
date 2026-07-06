## Overview

Fix the expense statement import flow so a parseable but previously unknown upload does not crash or block at mapping detection. Users should be able to manually map the uploaded file’s columns, save that mapping, and have the same file structure auto-detected on future uploads.

## Problem

The current import path can fail just after upload when the file parses but no saved/global mapping is available or AI mapping inference fails. That creates a poor recovery path: the user cannot inspect the detected headers, manually map the file, or save a mapping for later reuse.

## Proposed Outcome

1. Parseable unknown expense statement uploads reach the mapping review step instead of a 500 or blocking error.
2. The mapping review step can start with blank/manual field selections when no mapping is found.
3. Users can select columns, continue to row selection, and optionally save the mapping under a user-provided name.
4. Future uploads with the same normalized header signature automatically reuse the saved mapping.
5. AI mapping remains an optional prefill source, but AI/provider failures fall back to manual mapping review instead of crashing.

## Constraints / Non-Goals

- Do not commit the raw attached statement or any real customer/account data.
- Do not add a bank-specific importer unless a parser bug must be fixed generically for the attached file shape.
- Do not require live AI provider credentials for upload, mapping, tests, preview, or reviewer evidence.
- Do not create expenses until the user confirms selected preview rows.
- Do not build a global mapping management UI in this issue.
- Do not change unrelated manual expense, dashboard, invoice, or incoming-invoice behavior.
- Keep existing expense import route names compatible.
- Assumption: saved mappings remain private per user, matching the existing `ImportMapping` user/global scope model.

## Acceptance Criteria

### User Outcome

1. A user can upload a parseable statement with no matching saved/global mapping and see a mapping review page instead of a 500.
2. A user can manually map required fields, continue to row selection, and import selected rows.
3. A user can save the reviewed mapping with a name.
4. A later upload with the same header structure automatically uses the saved user mapping.
5. Corrupt or unparseable files still show a controlled in-page error and create no expenses.

### Technical Behavior

1. Upload handling persists parsed headers and raw rows before mapping inference is required to succeed.
2. Mapping resolution order remains selected mapping, user mapping, global mapping, AI prefill when available, then manual fallback.
3. AI provider errors, invalid AI output, and missing AI settings do not produce uncaught exceptions.
4. Manual fallback batches retain normalized header signatures and raw rows needed for review/save/reuse.
5. Review submission validates required mapping fields before preview rows are generated.
6. Saved mapping reuse does not call AI for matching future uploads.
7. Import batches, preview rows, and created expenses remain scoped to the authenticated user and active issuer.

### Operations / Deployment

1. No database migration is expected unless implementation discovers the existing import batch/mapping schema cannot represent manual fallback state.
2. Existing saved mappings and imported expenses remain valid.
3. Deployment does not require AI credentials or private attached files.
4. Normal build, migration, and static collection steps remain sufficient.

### Validation

1. Django tests cover unmatched parseable uploads reaching manual mapping review without AI settings.
2. Django tests cover AI provider failure falling back to manual mapping review without creating expenses.
3. Django tests cover saving a mapping from manual review and reusing it on a future same-header upload.
4. Django tests cover corrupt/unparseable uploads returning controlled errors.
5. Existing Wise/global mapping, selected mapping, AI-prefill, row selection, duplicate detection, CSV, XLS, XLSX, and ZIP import tests continue to pass.
6. Playwright reviewer evidence covers the manual mapping fallback and saved mapping reuse with sanitized committed fixtures.

## Implementation Plan

1. Trace the post-upload failure path for parsed statements with no matching mapping and for AI/provider exceptions.
2. Refactor upload handling so parsing and `ImportBatch` persistence can succeed before a valid mapping exists.
3. Add a manual mapping source/fallback that renders the existing mapping review controls with parsed headers and empty defaults.
4. Catch AI inference/provider failures and carry a non-blocking warning into the manual mapping review state.
5. Ensure review submission validates the user-selected mapping, saves named user mappings, builds preview rows, and preserves existing import confirmation behavior.
6. Add focused Django coverage and preview-safe Playwright evidence for manual mapping and mapping reuse.

## Task List

- [ ] Add manual mapping fallback after upload
  - [ ] Split upload parsing from mapping resolution so parsed headers/raw rows can be stored when no mapping exists.
  - [ ] Allow import batches to represent a manual/unmapped review state without creating preview rows yet.
  - [ ] Return manual mapping review when no selected, user, global, or AI mapping is usable.
  - [ ] Convert AI inference/provider exceptions into controlled manual-fallback feedback.
  - [ ] Add service and view tests for no-mapping/no-AI and AI-failure upload paths.

- [ ] Update mapping review, save, and reuse behavior
  - [ ] Render blank manual mapping controls using parsed upload headers.
  - [ ] Validate required mapping fields on review submission before generating preview rows.
  - [ ] Save named user mappings with the batch’s normalized header signature.
  - [ ] Reuse saved user mappings automatically on future same-header uploads.
  - [ ] Add tests for manual mapping save, row preview, import confirmation, and future auto-detection.

- [ ] Add issue-specific fixture and evidence automation
  - [ ] Add a sanitized regression fixture that preserves the attached file’s relevant header/table shape.
  - [ ] Extend `tests/e2e/expense-statement-import.spec.js` for manual fallback and saved mapping reuse.
  - [ ] Update `scripts/demo-evidence.sh` with the declared demo scenario identifier.
  - [ ] Update `scripts/visual-validation.sh` with the declared visual-validation identifier.
  - [ ] Keep generated screenshots, videos, databases, and raw uploads out of git.

## Deployment / Rollout

1. Deploy through the normal application pipeline.
2. Run migrations as usual; no schema migration is expected unless implementation adds one.
3. Existing mappings continue to work immediately after deploy.
4. After rollout, a parseable unknown import should be smoke-checked by uploading a sanitized statement, saving a mapping, and re-uploading the same-header statement.
5. If the attached file contains private data, only sanitized derivatives should be used for tests or evidence.

## File-Level Changes

### Add

- `tests/e2e/fixtures/expense-import/issue-146-unmatched-statement.*` — sanitized fixture preserving the attached file’s import-relevant shape.
- New Django tests in `expenses/tests/test_import_views.py` and/or `invoices/tests/test_expense_importer.py` for manual fallback and mapping reuse.

### Modify

- `expenses/views.py` — upload/review flow, AI error handling, manual fallback context, and mapping save/reuse behavior.
- `expenses/templates/expenses/expense_import.html` — manual mapping fallback copy and review-state feedback.
- `invoices/services/expense_importer.py` — mapping resolution, batch creation, and fallback behavior.
- `tests/e2e/expense-statement-import.spec.js` — reviewer evidence for manual mapping and saved mapping reuse.
- `scripts/demo-evidence.sh` — add `expense-import-manual-mapping` scenario.
- `scripts/visual-validation.sh` — add `expense-import-manual-mapping-fallback` capture identifier.

### Keep

- Existing `ImportMapping`, `ImportBatch`, and `ImportPreviewRow` schema unless a concrete gap is found.
- Existing Wise global mapping seed and mapping precedence.
- Existing CSV, XLS, XLSX, ZIP parsing support.
- Existing expense list, manual expense, dashboard, and incoming-invoice behavior.

## Demo Media

### Scenario: expense-import-manual-mapping

#### Repo Command

./scripts/demo-evidence.sh expense-import-manual-mapping

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned preview user flow and open the expense import page.
2. Upload a committed sanitized statement fixture that has no pre-seeded matching mapping and does not require live AI credentials.
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
3. In current mode, upload the sanitized unmatched statement and capture the manual mapping review state.
4. In current mode, save the mapping, upload a same-header statement again, and capture the saved-mapping reuse state.

### Full-Page Checkpoints

- expense-import-unmatched-mapping-full-page: full-page screenshot of the unmatched upload state
- expense-import-saved-mapping-reuse-full-page: full-page screenshot of the same-header upload after saving a mapping

### Expected Comparisons

- The unmatched-upload comparison should show the flow changing from a blocking/error state to an editable manual mapping review state.
- The saved-mapping reuse current capture should show a same-header upload using the saved mapping instead of requiring remapping.
- Reviewers should not see unrelated layout changes to the Expenses list or manual expense controls.

## Open Questions

- May the attached statement be sanitized into a committed regression fixture with real values removed, or should implementation use a synthetic fixture with the same header structure instead?
