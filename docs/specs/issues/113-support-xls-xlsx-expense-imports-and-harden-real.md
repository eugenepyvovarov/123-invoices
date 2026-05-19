## Overview

Extend the generic expense import flow so deterministic parsing supports CSV, XLS, XLSX, and existing ZIP-with-CSV statement uploads while preserving mapping review, row selection, duplicate detection, and import behavior.

Latest feedback clarifies the concrete regression inputs:
- The attached `01-07-05-2026-71419888f496.xlsx` should be sanitized into a committed regression fixture.
- The pasted semicolon CSV sample with comma decimals, `EUR` suffixes, and spaced thousands separators should become a second regression fixture.
- The OpenAI-compatible request path should have deterministic coverage plus an opt-in live smoke against `http://100.70.58.14:1234`, model `qwen/qwen3.6-27b`, and placeholder API key `1111`.

## Problem

The current importer supports CSV and ZIP-with-CSV uploads, but spreadsheet files can be accepted by upload paths and then routed through CSV or generic ZIP parsing. XLSX is especially risky because it is ZIP-based and can be mistaken for a ZIP bundle.

The real bank-export hardening target is no longer generic “CaixaBank” wording alone: implementation must handle a sanitized version of the attached XLSX workbook and the pasted semicolon CSV sample without uncaught importer exceptions.

The prior OpenAI-compatible provider work covered mocked/stubbed behavior and fixture-provider Playwright evidence, but did not validate the non-fixture HTTP request path against the requested live-compatible server.

## Proposed Outcome

1. Direct `.xls` and `.xlsx` uploads parse as spreadsheets and feed the existing normalized import pipeline.
2. CSV and ZIP-with-CSV behavior remains compatible.
3. Sanitized committed fixtures derived from the attached spreadsheet and pasted CSV sample reach stable importer behavior without server exceptions.
4. Localized bank values such as `-1 815,00EUR`, `+21,00EUR`, and `20/04/2026` normalize deterministically.
5. AI remains limited to mapping inference after deterministic parsing has produced headers and sample rows.
6. The OpenAI-compatible mapping client has deterministic fake-provider tests plus a repo-owned opt-in live smoke command for the requested server/model/key.
7. User-visible import copy describes supported statement files instead of CSV-only imports.

## Constraints / Non-Goals

- Do not use AI to parse, repair, or transform uploaded files.
- Do not send whole uploaded files to AI; only parsed headers and limited sample rows may be sent for mapping inference.
- Do not commit the raw attached bank export, live endpoint credentials, or screenshots containing secrets.
- Do not add a bank-specific CaixaBank importer or CaixaBank-only user flow.
- Do not require live AI credentials, private network access, or the raw issue attachment for CI, preview, Playwright reviewer evidence, or deployment.
- Do not remove existing Wise global mapping, saved mapping, row-selection, duplicate-detection, or manual expense behavior.
- Do not add multi-sheet selection UI in this issue.
- Keep existing `expenses:csv_import` route names compatible unless aliases are needed for clearer copy.

## Acceptance Criteria

### User Outcome

1. Users can upload CSV, XLS, XLSX, and ZIP-with-CSV expense statement files through the generic expense import flow.
2. Spreadsheet uploads reach the same mapping review, row selection, and import result flow as CSV uploads when their table can be parsed and mapped.
3. Existing CSV, ZIP-with-CSV, Wise global mapping, and saved mapping imports continue to work.
4. Sanitized fixtures based on the attached spreadsheet and pasted semicolon CSV render stable importer responses without server exceptions.
5. Import entry points and upload guidance clearly communicate supported statement file types.

### Technical Behavior

1. File dispatch identifies XLSX/XLS before generic ZIP handling.
2. XLSX files are parsed with `openpyxl` in read-only/data-only mode.
3. Legacy XLS files are parsed with `xlrd`.
4. Spreadsheet parsing converts detected headers and rows into the same row dictionaries used by existing mapping logic.
5. Parser logic tolerates blank rows, preamble rows, trailing summary rows, localized amount/date values, currency suffixes, plus/minus signs, and common bank-export encodings.
6. Unsupported, empty, corrupt, password-protected, or unmappable files raise controlled importer errors and do not create expenses.
7. AI mapping inference runs only after deterministic parsing succeeds and only when no selected, user, or global mapping matches.
8. The OpenAI-compatible client’s non-fixture HTTP path posts to `/v1/chat/completions`, sends only mapping-safe data, parses structured responses, and handles provider failures safely.
9. A repo-owned smoke command can target `http://100.70.58.14:1234` with model `qwen/qwen3.6-27b` and API key `1111`, while still allowing operator overrides.
10. Existing import mappings, header signatures, preview batches, duplicate detection, and raw-row traceability remain compatible.

### Operations / Deployment

1. Spreadsheet reader dependencies are included in the Python dependency set used by CI, preview, and deployment images.
2. No database migration is expected unless implementation discovers a required metadata/schema change.
3. Existing mappings and imported expenses require no data migration.
4. Deployment does not require live AI credentials, private network access, or live bank files.
5. Normal build, static collection, and migration steps remain sufficient for rollout.

### Validation

1. Django tests cover direct XLSX and XLS imports.
2. Django tests cover sanitized regressions for the attached spreadsheet and pasted semicolon CSV sample without uncaught exceptions.
3. Django tests preserve existing CSV and ZIP-with-CSV behavior.
4. Django tests cover localized amount/date parsing and corrupt spreadsheet error handling.
5. Django tests cover the OpenAI-compatible non-fixture HTTP request path against a deterministic local fake provider.
6. The live smoke command is documented and runnable against `http://100.70.58.14:1234` with `qwen/qwen3.6-27b` and API key `1111` when the private server is reachable.
7. Existing CSV, Wise, saved mapping, AI fixture mapping, row selection, and duplicate tests continue to pass.
8. Playwright reviewer evidence uses committed sanitized fixtures and deterministic fixture/saved mapping behavior, not live credentials.

## Implementation Plan

1. Add spreadsheet parsing dependencies: `openpyxl` for XLSX and `xlrd` for XLS.
2. Refactor upload parsing around a statement parser dispatch that checks XLSX/XLS before generic ZIP handling.
3. Implement spreadsheet row extraction with first visible detectable worksheet, stable header detection, string conversion, spreadsheet dates, and controlled errors.
4. Replace CSV-only parser naming/copy with statement-file naming while preserving current route compatibility where practical.
5. Add sanitized committed fixtures derived from the attached XLSX workbook and pasted semicolon CSV sample.
6. Harden generic table parsing and normalization around preambles, blank rows, localized amounts/dates, `EUR` suffixes, plus/minus signs, encodings, and malformed rows.
7. Add deterministic OpenAI-compatible HTTP request-path coverage using a local fake provider distinct from the fixture shortcut.
8. Add a repo-owned opt-in live smoke command for the requested OpenAI-compatible endpoint/model/key.
9. Update importer UI copy, upload accept extensions, AI mapping copy, Django tests, and Playwright reviewer evidence.

## Task List

- [x] Add deterministic statement parsing for CSV, XLS, XLSX, and ZIP-with-CSV
  - [x] Add `openpyxl` and `xlrd` to `requirements.txt`.
  - [x] Introduce a parser dispatch helper that detects XLSX/XLS before generic ZIP detection.
  - [x] Implement XLSX parsing with read-only/data-only workbook handling and worksheet/header detection.
  - [x] Implement XLS parsing with equivalent row/header extraction and spreadsheet date handling.
  - [x] Preserve existing CSV and ZIP-with-CSV behavior through the same normalized parsed-file contract.
  - [x] Add importer tests for direct XLSX, direct XLS, CSV, ZIP-with-CSV, empty files, and corrupt spreadsheet files.

- [x] Harden real bank export parsing through generic normalization
  - [x] Add a committed sanitized XLSX fixture that preserves the attached workbook’s sheet/header/data shape without real account data.
  - [x] Add a committed CSV fixture based on the pasted `Item;Date;Amount;Balance` sample.
  - [x] Add table/header detection that can skip workbook preamble, blank rows, and trailing non-transaction rows.
  - [x] Normalize localized amount strings with comma decimals, space thousands separators, `EUR` suffixes, and leading plus/minus signs.
  - [x] Normalize date values from CSV strings and spreadsheet cells without breaking existing formats.
  - [x] Convert parser failures into controlled importer errors and assert no expenses are created on failure.

- [x] Add deterministic and live OpenAI-compatible request-path coverage
  - [x] Add a local fake OpenAI-compatible HTTP provider test for `OpenAICompatibleMappingClient`.
  - [x] Assert the request uses the expected chat-completions endpoint, authorization header, model, response schema, and limited sample rows.
  - [x] Assert the client parses valid structured responses and surfaces invalid/failed provider responses safely.
  - [x] Add a Django management command or committed script for opt-in live smoke against `http://100.70.58.14:1234`, `qwen/qwen3.6-27b`, and default API key `1111`.
  - [x] Ensure the live smoke sends only sanitized headers/sample rows and never commits credentials or raw bank files.

- [x] Update importer UI and user-visible copy
  - [x] Update the Expenses import entry point, import page heading/subtitle, file label, accepted extensions, and validation copy.
  - [x] Update project/customer profile import links that still say CSV-only.
  - [x] Update AI provider/settings copy from CSV-only mapping to statement/header mapping.
  - [x] Keep legacy route names or add compatible aliases unless renaming is necessary.
  - [x] Update view/template tests for supported upload types and controlled error feedback.

- [x] Add issue-specific Playwright evidence code
  - [x] Add or replace the CSV-only Playwright spec with `tests/e2e/expense-statement-import.spec.js`.
  - [x] Add committed sanitized XLSX, XLS, and semicolon CSV fixtures for evidence and regression coverage.
  - [x] Use deterministic fixture or saved mapping setup so evidence does not require live provider credentials.
  - [x] Capture the Demo Media and Visual Validation checkpoints named in this spec.

## Deployment / Rollout

1. Deploy through the normal build path so spreadsheet dependencies are installed before uploads are handled.
2. Run migrations as usual; no schema change is expected.
3. Existing import mappings remain valid because spreadsheets feed the same normalized header/signature path.
4. Existing Wise, CSV, and ZIP-with-CSV imports should continue to work immediately after deployment.
5. CI and reviewer evidence must not depend on the private OpenAI-compatible endpoint.
6. When the private endpoint is reachable, operators should run the documented live smoke command with API key `1111` or an override key and record the result.
7. If the private endpoint is unreachable from the runner, report it as an environment limitation rather than blocking CI-safe validation.

## File-Level Changes

### Add

- `invoices/services/expense_statement_parsers.py` — focused statement parser helpers.
- `invoices/management/commands/smoke_expense_import_ai_provider.py` — opt-in live OpenAI-compatible smoke command.
- `tests/e2e/expense-statement-import.spec.js` — issue-specific Playwright evidence scenarios.
- `tests/e2e/fixtures/expense-import/caixabank-attached.xlsx` — sanitized fixture derived from the attached workbook.
- `tests/e2e/fixtures/expense-import/caixabank-semicolon.csv` — fixture based on the pasted CSV sample.
- `tests/e2e/fixtures/expense-import/legacy-statement.xls` — sanitized legacy XLS fixture for parser coverage.
- `invoices/tests/test_expense_import_ai.py` — focused OpenAI-compatible client request-path tests if split from the existing importer test module.

### Modify

- `requirements.txt` — add spreadsheet parser dependencies.
- `invoices/services/expense_importer.py` — dispatch by statement type, integrate parser helpers, harden normalization, and update CSV-only errors.
- `invoices/services/expense_import_ai.py` — keep AI limited to mapping inference and support request-path tests/smoke behavior.
- `expenses/views.py` and `expenses/urls.py` — update import validation/error handling while preserving compatible routes as needed.
- `expenses/templates/expenses/expenses_list.html` — update import entry point wording.
- `expenses/templates/expenses/expense_import.html` — update heading, guidance, accepted extensions, labels, and feedback copy.
- `invoices/templates/invoices/project_detail.html` — update import link wording.
- `invoices/templates/invoices/customer_profile.html` — update import link wording.
- `accounts/forms.py` and `accounts/templates/accounts/user_settings.html` — update AI mapping copy from CSV-only to statement/header wording.
- `invoices/tests/test_expense_importer.py` — add spreadsheet, attached-workbook, semicolon CSV, ZIP, and normalization regressions.
- `expenses/tests/test_import_views.py` — update view expectations for statement-file wording and supported uploads.
- `accounts/tests/test_user_settings.py` — update AI-provider copy expectations if needed.
- `tests/e2e/expense-csv-import.spec.js` — rename, replace, or explicitly retire after adding statement-import scenarios.

### Keep

- Existing `ImportMapping`, `ImportBatch`, and `ImportPreviewRow` persistence unless a specific schema gap is found.
- Existing Wise global mapping seed and mapping precedence.
- Existing saved mapping, AI fixture mapping, row selection, duplicate detection, and expense creation behavior.
- Existing manual expense creation/editing/list behavior.
- Existing preview-backed Playwright evidence infrastructure.

## Visual Validation

### Identifier

expense-statement-import-file-types

### Capture Command

`./scripts/e2e.sh tests/e2e/expense-statement-import.spec.js --grep "expense-statement-import-visual"`

### Steps

1. Capture the Expenses page full-page state showing the import entry point with statement-file wording.
2. Capture the import upload page full-page state showing CSV, XLS, XLSX, and ZIP guidance.
3. Capture the full-page mapping review state after uploading the sanitized XLSX fixture.
4. Capture the full-page row-selection state after the XLSX fixture is parsed.
5. Capture the full-page stable importer state after uploading the semicolon CSV fixture.

### Full-Page Checkpoints

- `expense-statement-import-entry-full-page`
- `expense-statement-import-upload-guidance-full-page`
- `expense-caixabank-xlsx-mapping-review-full-page`
- `expense-caixabank-xlsx-row-selection-full-page`
- `expense-caixabank-csv-stable-response-full-page`

### Expected Comparisons

- Reviewers should see CSV-only wording replaced with statement-file wording that includes spreadsheet support.
- Reviewers should see spreadsheet uploads use the existing mapping and preview UI instead of an error/crash state.
- Reviewers should see the semicolon CSV regression fixture handled inside the importer page rather than by a server exception.
- Reviewers should not see unrelated changes to the Expenses list layout or manual expense controls.

### Baseline SHA

`2c556f8ea9729093d8356f9b3a67ba9df84c597b`


## Demo Media

Source-of-truth note: define issue-specific statement import scenarios for this work. Do not infer reuse from the older CSV-only demo path unless it is explicitly updated to the scenario identifiers and commands below.

### Scenario: expense-caixabank-xlsx-import

#### Repo Command

`./scripts/e2e.sh tests/e2e/expense-statement-import.spec.js --grep "expense-caixabank-xlsx-import"`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open the Expenses page and show the import entry point with statement-file wording.
3. Open the import page and upload the committed sanitized XLSX fixture derived from the attached workbook.
4. Show the mapping review state using a saved mapping or deterministic fixture mapping behavior.
5. Continue to row selection and show parsed spreadsheet rows in the existing preview UI.
6. Confirm selected rows and show the resulting import summary or redirected Expenses state.

#### Screenshot Checkpoints

- `expense-statement-import-entry-full-page`
- `expense-caixabank-xlsx-upload-full-page`
- `expense-caixabank-xlsx-mapping-review-full-page`
- `expense-caixabank-xlsx-row-selection-full-page`
- `expense-caixabank-xlsx-result-full-page`

### Scenario: expense-caixabank-semicolon-csv-import

#### Repo Command

`./scripts/e2e.sh tests/e2e/expense-statement-import.spec.js --grep "expense-caixabank-semicolon-csv-import"`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow.
2. Open the generic expense import page.
3. Upload the committed semicolon CSV fixture based on the pasted sample.
4. Show the stable importer response after deterministic CSV parsing and localized value normalization complete.
5. Continue through the existing mapping/preview flow without relying on live provider credentials.

#### Screenshot Checkpoints

- `expense-caixabank-csv-upload-full-page`
- `expense-caixabank-csv-stable-response-full-page`
- `expense-caixabank-csv-preview-full-page`

## Demo Scenario

### Scenario Identifier

expense-caixabank-xlsx-import

### Repo Command

`./scripts/e2e.sh tests/e2e/expense-statement-import.spec.js --grep "expense-caixabank-xlsx-import"`

### Screenshot Checkpoints

- `expense-statement-import-entry-full-page`
- `expense-caixabank-xlsx-upload-full-page`
- `expense-caixabank-xlsx-mapping-review-full-page`
- `expense-caixabank-xlsx-row-selection-full-page`
- `expense-caixabank-xlsx-result-full-page`

## Open Questions

None.
