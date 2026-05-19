# Overview

Add the existing recent tasks / recently used items experience to the draft invoice edit form, and make that area collapsible in both create and draft-edit flows. The recommended cut is to reuse the current recent-items payload and project lookup behavior, with a shared UI/JS path instead of duplicating the create-page inline script.

# Problem

The new invoice form renders recently used project items so users can copy prior task lines into the invoice. The invoice edit route already prepares `recent_items_data`, but the main invoice profile edit tab does not render the recent-items UI, so reopening a saved draft loses that shortcut.

The current implementation also has duplicated recent-items behavior across form surfaces, and the project recent-items endpoint does not currently have an edit-aware way to exclude the invoice being edited.

# Proposed Outcome

- The invoice create form and draft invoice edit tab both expose a clear show/hide control for recent tasks.
- When expanded, the recent tasks area shows project-specific prior order-line items and lets users copy one into the order lines without submitting the form.
- When collapsed, the area becomes compact without clearing unsaved header, notes, or order-line input.
- Draft edit uses the same recent-item source as create, but excludes the invoice currently being edited.
- Project changes refresh the recent tasks list consistently in create and draft-edit flows.
- Non-draft invoice edit rules remain unchanged; this issue must not create a new path for unsafe non-draft task editing.

Assumption: show/hide state only needs to persist while the current form page is open; no database-backed or account-level preference is required.

# Constraints / Non-Goals

- Do not add migrations, new models, or a persisted UI preference.
- Do not redesign the invoice form, preview tab, payment drawer, PDF generation, totals calculation, or order-line table.
- Do not change recent-item ranking/deduplication except where needed to exclude the currently edited invoice.
- Do not broaden non-draft invoice mutability.
- Do not require local-only manual seed steps for reviewer evidence.

# Acceptance Criteria

## User Outcome

1. Creating a new invoice still provides access to recent project tasks.
2. Opening an existing draft invoice on the edit tab provides access to recent project tasks.
3. Both create and draft-edit flows include a clear show/hide control for the recent tasks area.
4. Hiding and showing recent tasks does not clear unsaved invoice fields, notes, or order-line input.
5. Adding a recent task populates an order-line row using the existing order-line behavior.
6. Non-draft invoice screens do not gain new unsafe task-edit affordances beyond the current rules.

## Technical Behavior

1. The existing recent-items query behavior remains the source of recent tasks.
2. Draft-edit recent tasks exclude the invoice currently being edited on initial render and project-change fetches.
3. Optional exclude behavior on the project recent-items endpoint is scoped to the active issuer and does not leak cross-company invoice data.
4. The recent-tasks UI can initialize safely on create, draft edit, and any retained drawer form without double-binding handlers.
5. The show/hide control uses non-submit button behavior and exposes appropriate expanded/collapsed state for assistive technologies.

## Operations / Deployment

1. No migration, environment variable, feature flag, or operator setup step is required.
2. Normal static collection/build behavior is sufficient if shared JavaScript or CSS is added.
3. Preview-backed reviewer evidence uses the spec-declared Playwright command.

## Validation

1. Django tests cover create-form recent task availability.
2. Django tests cover draft-edit recent task rendering and current-invoice exclusion.
3. Django tests cover the project recent-items endpoint with and without the edit exclusion parameter.
4. Playwright coverage exercises show/hide behavior, unsaved form preservation, and add-from-recent behavior for create and draft-edit flows.

# Demo Media

Source-of-truth note: do not infer reuse from existing invoice Playwright tests. Add or update the issue-specific scenario below and use this command for reviewer evidence.

### Scenario: invoice-recent-tasks-create

#### Repo Command

`./scripts/e2e.sh tests/e2e/invoice-recent-items.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow and open the new invoice form with an active project that has prior invoice line history.
2. Show the recent tasks area in the invoice form.
3. Enter unsaved invoice form input, collapse the recent tasks area, then expand it again.
4. Use one recent task add action and leave the populated order-line row visible without submitting the invoice.

#### Screenshot Checkpoints

- `invoice-create-recent-tasks-expanded`
- `invoice-create-recent-tasks-collapsed`
- `invoice-create-recent-task-added`

### Scenario: invoice-recent-tasks-draft-edit

#### Repo Command

`./scripts/e2e.sh tests/e2e/invoice-recent-items.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow and open an existing draft invoice on the edit tab.
2. Show the recent tasks area within the draft invoice edit form.
3. Change unsaved invoice form input, collapse the recent tasks area, then expand it again.
4. Use one recent task add action and leave the populated order-line row visible without changing the invoice status or submitting a non-draft edit.

#### Screenshot Checkpoints

- `draft-invoice-edit-recent-tasks-expanded`
- `draft-invoice-edit-recent-tasks-collapsed`
- `draft-invoice-edit-recent-task-added`

# Visual Validation

No existing visual path is reused implicitly. Use the same issue-specific Playwright command as Demo Media.

### Identifier

invoice-recent-tasks-form-layout

### Capture Command

`./scripts/e2e.sh tests/e2e/invoice-recent-items.spec.js`

### Steps

1. Open the new invoice form with a selected project and capture the full page with recent tasks expanded.
2. Open an existing draft invoice on the edit tab and capture the full page with recent tasks expanded.
3. Collapse the recent tasks area on the draft edit form and capture the full page compact state.

### Full-Page Checkpoints

- `invoice-create-recent-tasks-full-page`
- `draft-invoice-edit-recent-tasks-full-page`
- `draft-invoice-edit-recent-tasks-collapsed-full-page`

### Expected Comparisons

- Reviewers should see the create form still includes recent tasks, now with a clear show/hide control.
- Reviewers should see the draft edit form gains the same recent tasks capability in the form context where it was previously missing.
- Reviewers should see the collapsed draft-edit state reduces the recent tasks area while preserving the surrounding form fields and order-line area.
- Reviewers should not see unrelated changes to invoice preview, payment, or non-draft status surfaces.

### Baseline SHA

`43e93a196d4ee749b621fcb0c4d80dd93f0a14eb`


# Implementation Plan

1. Add a shared recent-tasks form component, preferably a template partial plus static JavaScript initializer, so create and edit flows do not maintain separate recent-item implementations.
2. Update the create invoice form to use the shared component while preserving existing selected-project and initial recent-items behavior.
3. Update the invoice profile edit tab to render the shared component for draft/editable invoice forms using the existing `recent_items_data` and `selected_project_id` context.
4. Extend recent-items fetching so draft edit can pass the current invoice id as an exclusion, and validate that exclusion against the active issuer.
5. Ensure the show/hide behavior hides only the recent-tasks UI, not the form state or order-line manager state.
6. Add Django and Playwright coverage for create, draft edit, current-invoice exclusion, and compact/expanded UI behavior.

# Task List

- [x] Share recent-tasks UI and client behavior
  - [x] Add reusable recent-tasks markup with a toggle control, content container, selected-project data, and initial JSON payload.
  - [x] Move recent-items render/fetch/add behavior into a shared static JavaScript initializer.
  - [x] Ensure the toggle is a non-submit control and updates expanded/collapsed state without remounting form fields.
  - [x] Keep add-from-recent integrated with the existing order-line manager and totals updates.
  - [x] Add template/render assertions for the create form’s recent-tasks control.

- [x] Add draft-edit recent tasks safely
  - [x] Render the shared recent-tasks component in the invoice profile edit tab for draft/editable invoice forms.
  - [x] Pass the current invoice id as an exclusion source for draft-edit initial data and project-change fetches.
  - [x] Update the project recent-items endpoint to honor a validated optional invoice exclusion.
  - [x] Cover draft-edit visibility, current-invoice exclusion, and non-draft rule preservation in Django tests.

- [x] Keep existing invoice form surfaces consistent
  - [x] Reconcile the existing drawer recent-items markup with the shared behavior or keep it explicitly compatible without regressions.
  - [x] Ensure project changes refresh recent tasks consistently across create and draft-edit forms.
  - [x] Prevent double initialization when the invoice profile page has tabs, form scripts, and optional drawer code loaded together.

- [x] Add invoice recent-items E2E coverage
  - [x] Add `tests/e2e/invoice-recent-items.spec.js` using the existing smoke authentication flow.
  - [x] Exercise create and draft-edit show/hide behavior with unsaved form preservation.
  - [x] Capture the named full-page demo and visual-validation checkpoints from the committed scenario.

# Deployment / Rollout

This is a low-risk view/template/static-JS rollout.

1. Deploy through the normal application release path.
2. No database migration or environment update is expected.
3. Run targeted Django invoice tests and the spec-declared Playwright command before merge.
4. After deploy, smoke-check invoice creation and draft invoice editing with a project that has prior invoice lines.

# File-Level Changes

## Add

- `invoices/templates/invoices/partials/recent_items.html` — shared toggleable recent-tasks markup.
- `invoices/static/invoices/js/recent_items.js` — shared recent-items initialization, fetch, toggle, and add behavior.
- `tests/e2e/invoice-recent-items.spec.js` — issue-specific Playwright regression and reviewer-evidence scenario.

## Modify

- `invoices/templates/invoices/form_invoice.html` — use the shared recent-tasks component instead of the page-local implementation.
- `invoices/templates/invoices/invoice_profile.html` — render recent tasks in the draft invoice edit form and include the shared initializer.
- `invoices/templates/invoices/partials/invoice_form_inner.html` — align the drawer form with the shared behavior if the shared initializer replaces existing drawer logic.
- `invoices/views.py` — preserve current recent-items context and add validated current-invoice exclusion for project recent-items fetches.
- `invoices/tests/test_invoices.py` — cover create visibility, draft-edit visibility, endpoint exclusion, and non-draft rule preservation.
- `invoices/static/invoices/css/design/components.css` — add narrowly scoped styling only if the toggle/collapsed state needs it.

## Keep

- `invoices/models.py` and existing migrations — no schema change is expected.
- `invoices/templates/invoices/partials/order_lines_table.html` — keep order-line behavior and integrate through the existing JavaScript API.
- `invoices/static/invoices/js/order_lines.js`, `invoice_dates.js`, and `invoice_totals.js` — preserve existing form calculations and line management.
- `scripts/e2e.sh` and `playwright.config.js` — reuse the existing managed Playwright runner.

# Open Questions

None.
