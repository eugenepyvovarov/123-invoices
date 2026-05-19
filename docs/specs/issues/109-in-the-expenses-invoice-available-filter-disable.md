# Overview

Keep the Expenses page’s `Invoice available` filter active when an expense attachment is uploaded, removed, or otherwise changed from the expense drawer. Replace the current save/delete page reload behavior with an in-place expenses list refresh that uses the current filters.

# Problem

The expense drawer saves via AJAX, but successful saves currently navigate back to the bare Expenses list. When a user is filtering by `Invoice available`, uploading or removing an attachment resets the page to the default filter state, making the active filter appear disabled and forcing the user to reapply it.

# Proposed Outcome

Expense changes made from the Expenses page should preserve the current filter context and refresh the visible expense history in place.

Recommended cut:

- Preserve `date_range`, `has_attachment`, `q`, `order`, and pagination/search context when saving or deleting expenses.
- After drawer save or delete, close the drawer and refresh the expense list/table/summary/pagination using the current query string.
- If the edited expense no longer matches the active `Invoice available` filter, the refreshed list should reflect that naturally.
- Keep non-JavaScript or fallback responses safe by redirecting back to the filtered Expenses URL instead of the bare list.
- Assumption: this issue covers expense drawer create/edit/delete and attachment upload/remove behavior on `/expenses/`; Wise import and bulk download behavior remain out of scope.

# Constraints / Non-Goals

- Do not change expense filtering semantics or add new filter values.
- Do not change attachment validation rules, storage behavior, file type limits, or max upload size.
- Do not introduce a full SPA framework; keep this as progressive enhancement around the existing Django views/templates and vanilla JS.
- Do not change the existing bulk download workflow.
- Do not require migrations, new environment variables, or feature flags.
- Preserve current access control through the active issuer/company context.

# Acceptance Criteria

## User Outcome

1. When `Invoice available = Without file` is active and a user uploads an attachment to a visible expense, the Expenses page remains on the same filter after save.
2. When `Invoice available = With file` is active and a user removes an attachment from a visible expense, the Expenses page remains on the same filter after save.
3. After save or delete, the expense history visibly refreshes without resetting the filter panel to `All`.
4. The drawer closes after a successful save, and the user receives in-place feedback that the change completed.
5. The current search and period filters remain applied during the in-place refresh.

## Technical Behavior

1. Expense drawer POST responses support refreshing the list for the caller’s current filtered Expenses URL.
2. Expense delete responses support the same filtered list refresh behavior as drawer saves.
3. Fallback redirects use a sanitized internal Expenses URL with the current query string, not an external URL and not the unfiltered bare list.
4. Refreshed expense list fragments include the table rows, record count/total, pagination state, bulk-download `next` target, and any UI state needed for follow-up row interactions.
5. Existing async reporting visibility toggles continue to work after the list fragment is replaced.

## Operations / Deployment

1. The change ships through the normal Django/static asset deploy path.
2. No database migration, manual data repair, or operator configuration is required.
3. Static asset collection remains sufficient if JavaScript or CSS is changed.

## Validation

1. Django tests cover filtered drawer saves for attachment upload/removal and verify the filtered context is preserved.
2. Django tests cover delete behavior with a filtered `next` URL and unsafe `next` URL rejection.
3. JavaScript-facing response tests verify successful mutations can return refreshed list fragments instead of a bare redirect.
4. A Playwright scenario captures reviewer evidence for attachment upload/removal while the `Invoice available` filter remains active.

# Demo Media

Explicit reuse note: do not reuse an older Playwright scenario implicitly. Add or update the issue-specific scenario below and use its repo command as the source of truth.

### Scenario: expense-attachment-filter-refresh

#### Repo Command

`./scripts/e2e.sh tests/e2e/expense-attachment-filter-refresh.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow and navigate to `/expenses/`.
2. Create or select a uniquely identifiable expense without an attachment using the visible Expenses UI.
3. Apply the `Invoice available` filter for expenses without files and keep the unique expense visible under that filtered state.
4. Open the expense drawer, upload a committed small supported attachment fixture, and save.
5. Confirm the drawer closes and the Expenses page remains in the same filtered page context while the history refreshes in place.
6. Navigate to the with-file filtered state for the same expense, open the drawer, remove the attachment, and save.
7. Confirm the drawer closes and the Expenses page remains in the with-file filtered page context while the history refreshes in place.

#### Screenshot Checkpoints

- `expenses-without-file-filter-before-upload` — full-page screenshot of the Expenses page with the without-file filter active before uploading.
- `expenses-without-file-filter-after-upload` — full-page screenshot after saving an uploaded attachment while the same filter context remains visible.
- `expenses-with-file-filter-after-remove` — full-page screenshot after removing the attachment while the with-file filter context remains visible.

# Visual Validation

Explicit reuse note: visual capture should use the same issue-specific Playwright command as Demo Media; no older visual path is reused implicitly.

### Identifier

expense-attachment-filter-refresh

### Capture Command

`./scripts/e2e.sh tests/e2e/expense-attachment-filter-refresh.spec.js`

### Steps

1. Reach the Expenses page through the repo-owned smoke-user flow.
2. Capture the full page with the `Invoice available` without-file filter active before uploading an attachment to the selected expense.
3. Upload the attachment through the drawer, save, wait for the in-place refresh, and capture the full page again with the filtered Expenses page still visible.
4. Remove the attachment through the drawer from the with-file filtered state, save, wait for the in-place refresh, and capture the full page again with the filtered Expenses page still visible.

### Full-Page Checkpoints

- `expenses-without-file-filter-before-upload`
- `expenses-without-file-filter-after-upload`
- `expenses-with-file-filter-after-remove`

### Expected Comparisons

- Reviewers should see the Expenses page stay in the relevant `Invoice available` filtered context instead of returning to `All`.
- The filter panel, search/period context, and expense history area should remain visually stable while the list content updates.
- The changed expense should move in or out of the filtered result naturally based on whether it currently has an attachment.
- No focused or cropped screenshots are required because the relevant filter state and refreshed list are visible in full-page context.

### Baseline SHA

`b6ad1a281db5ee0670144f413ce56360e481c917`


# Implementation Plan

1. Extract the expense history/table summary/pagination area into a reusable partial or helper-backed render path that can serve both the full page and async refresh responses.
2. Add a safe current-list URL/query contract for drawer save and delete requests, preserving only internal `/expenses/` URLs.
3. Update `expense_drawer` and `expense_delete` success responses so async callers receive refreshed list HTML/fragments and fallback callers can return to the filtered URL.
4. Update `expenses_drawer.js` to submit the current Expenses URL/query, close the drawer on success, replace the refreshed list regions, update bulk form `next`, and reinitialize row-level async controls.
5. Add in-place success/error feedback for async saves/deletes without depending on a full page reload.
6. Add Django coverage for filtered attachment upload/removal/delete behavior and add the issue-specific Playwright scenario with screenshot checkpoints.

# Task List

- [x] Add reusable filtered expense list rendering
  - [x] Extract the expense history summary, table, pagination, and bulk `next` state into a partial or helper-rendered fragment.
  - [x] Keep the existing full-page `/expenses/` render output equivalent for normal GET requests.
  - [x] Ensure refreshed fragments are built from the same `date_range`, `has_attachment`, `q`, `order`, and `page` query inputs as the full page.
  - [x] Add Django tests for the filtered fragment context where attachment availability changes.

- [x] Preserve filter context through drawer save/delete
  - [x] Add a sanitized current-list URL/query input for drawer form submissions and delete requests.
  - [x] Return refreshed list data for async successful drawer saves, including attachment upload and removal cases.
  - [x] Return refreshed list data for async deletes while keeping unsafe fallback URLs rejected.
  - [x] Update drawer/delete view tests for filtered success responses and safe fallback behavior.

- [x] Update Expenses page JavaScript refresh behavior
  - [x] Replace successful drawer-save navigation with close-drawer plus in-place list refresh.
  - [x] Replace successful delete reload with the same filtered in-place list refresh.
  - [x] Keep filter form controls, URL query context, bulk selection state, and reporting visibility toggles usable after fragment replacement.
  - [x] Surface non-blocking success/error feedback for async mutation outcomes.

- [x] Add issue-specific Playwright evidence coverage
  - [x] Add a small committed supported attachment fixture for the expense drawer upload scenario.
  - [x] Add `tests/e2e/expense-attachment-filter-refresh.spec.js` for upload/remove behavior under active `Invoice available` filters.
  - [x] Capture the named full-page checkpoints declared in Demo Media and Visual Validation.

# Deployment / Rollout

This is a low-risk Django template/view/static JavaScript rollout.

1. Deploy through the normal release path.
2. Run the standard build/collectstatic flow if static JavaScript changes are included.
3. No migration, data backfill, or environment update is expected.
4. Before release, rely on the Django tests and the spec-declared Playwright command for behavior and reviewer-evidence validation.

# File-Level Changes

## Add

- `tests/e2e/expense-attachment-filter-refresh.spec.js` — issue-specific Playwright scenario for preserving attachment filters during async expense changes.
- `tests/e2e/fixtures/expenses/` fixture file — small supported attachment file used by the Playwright upload flow.
- Optional `expenses/templates/expenses/partials/expense_list_results.html` — reusable filtered expense history/table/pagination fragment if the implementation chooses a partial-based refresh.

## Modify

- `expenses/views.py` — centralize filtered list rendering and return refreshed fragments/safe redirects for drawer save and delete.
- `expenses/templates/expenses/expenses_list.html` — wrap or include refreshable expense list regions and expose the current filtered list URL to JavaScript.
- `expenses/templates/expenses/partials/expense_drawer.html` — include current-list context if needed for drawer submissions.
- `invoices/static/invoices/js/expenses_drawer.js` — replace full reload/redirect behavior with filtered in-place refresh and reinitialization.
- `expenses/tests/test_drawer_views.py` — cover filtered drawer saves and refreshed async responses.
- `expenses/tests/test_list_views.py` — cover preserved filter behavior, safe next URLs, and delete refresh behavior.

## Keep

- `expenses/forms.py` — existing attachment validation and remove-attachment form behavior should remain unchanged unless a small hidden field is needed.
- `expenses/urls.py` — no new route is required unless the implementation chooses a dedicated list-fragment endpoint.
- `invoices/models.py` and migrations — no schema change is expected.
- `scripts/e2e.sh` and `playwright.config.js` — reuse the existing Playwright runner/config.

# Open Questions

None.
