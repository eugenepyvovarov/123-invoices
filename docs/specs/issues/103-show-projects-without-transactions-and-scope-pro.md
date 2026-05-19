# Overview

Make projects visible as project records even when they have no transactions, and replace global project-code uniqueness with company-scoped uniqueness.

Recommendation: treat “company” as the active issuing company/issuer because project views already scope records through `customer__issuer`. This is called out in Open Questions because choosing client/customer company instead would change the migration and constraint design.

# Problem

The Projects list currently appears to depend on invoice-derived balances. In `view_projects`, projects are annotated with invoice totals and then filtered to rows with pending or paid totals, which hides projects that have no non-draft invoice activity in the selected date range.

`Project.project_code` is also globally unique at the model/database level, so two separate companies cannot use the same project code even though users expect codes to be reusable across companies.

# Proposed Outcome

- Project list visibility is based on active company and project status, not on whether a project has invoices, payments, or non-zero balances.
- Date filters continue to affect displayed project totals, but do not remove projects from the list solely because totals are zero.
- Active transactionless projects remain selectable where users create invoices for active customers.
- Existing transaction-backed project totals, links, ordering, and company isolation continue to work.
- Project code uniqueness is enforced only inside the chosen company scope, while different companies can reuse the same code.
- Add database/form/model enforcement for scoped project codes rather than relying only on view-level checks.

# Constraints / Non-Goals

- Do not redesign the Projects table, project form, invoice form, or payment drawer UI.
- Do not expose projects from another active company/issuer.
- Do not make inactive projects selectable in new invoice flows unless they are already allowed by existing behavior.
- Do not change invoice, payment, or cached-total calculations.
- Keep bulk last-month invoice generation restricted to projects with prior invoice lines; that flow intentionally depends on transaction-backed history.
- If issuer-scoped uniqueness is confirmed, do not use `customer + project_code` as the database constraint because that would allow duplicate codes across customers inside the same issuing company.

# Acceptance Criteria

## User Outcome

1. A project with no invoices, payments, or order lines appears in the Projects list for its active company when its status filter matches.
2. A project with existing transaction-backed invoice activity still appears and shows its totals as before.
3. Date filters change the displayed paid/pending totals but do not hide otherwise matching projects whose in-period totals are zero.
4. An active project with no transactions is available in the new-invoice project selection flow when its customer is active.
5. Duplicate project codes are rejected inside the chosen company scope.
6. The same project code can be used by projects in different companies.

## Technical Behavior

1. `view_projects` no longer filters the annotated project queryset by `pending_balance > 0` or `paid_total > 0`.
2. Project list, detail, form, invoice, and payment-related project queries remain scoped to the active issuer/company.
3. `Project.project_code` is no longer globally unique.
4. A database-level uniqueness constraint and form/model validation enforce company-scoped project codes.
5. Existing status filtering, sorting, two-decimal monetary display, and customer links remain intact.
6. Bulk last-month candidate generation remains based on prior invoices and is not expanded to transactionless projects.

## Operations / Deployment

1. A schema migration is included if database constraints or denormalized company/issuer scope fields are needed.
2. Existing project rows are backfilled into the chosen company scope before the scoped uniqueness constraint is applied.
3. Existing globally unique project codes should not require duplicate cleanup before relaxing the global constraint, but the migration should fail clearly if unexpected same-scope duplicates are present.
4. No new environment variables, feature flags, or operational services are required.

## Validation

1. Django tests cover Projects list visibility for transactionless and transaction-backed projects.
2. Django tests cover active-company isolation for Projects list and project selectors.
3. Django tests cover same-company duplicate project-code rejection and cross-company duplicate-code allowance.
4. Django tests cover add/edit ProjectForm validation for scoped duplicates.
5. Playwright reviewer evidence captures the Projects list and invoice project-selection state with a transactionless project visible.

# Demo Media

Source-of-truth note: define a new issue-specific scenario for this task. Do not infer reuse from older Playwright specs unless this spec is explicitly updated.

### Scenario: transactionless-project-visibility

#### Repo Command

`./scripts/e2e.sh tests/e2e/project-visibility.spec.js`

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned Playwright smoke-user flow and use an active company visible to that user.
2. Through preview-safe app UI setup inside the scenario, ensure the active company has an active customer, one transaction-backed project, and one active project with no invoices or payments. Reuse existing matching records if they are already present.
3. Navigate to the Projects list with an active-project status filter and an all-time date range.
4. Capture the Projects list after it settles, showing the transactionless project in the same reviewer-visible table context as transaction-backed projects.
5. Navigate to the new-invoice form.
6. Select the transactionless project in the project field without saving an invoice.
7. Capture the full page with the transactionless project selected in the invoice form.

#### Screenshot Checkpoints

- `projects-list-transactionless-project`
- `invoice-form-transactionless-project-selected`

# Visual Validation

### Identifier

project-transactionless-visibility

### Capture Command

`./scripts/e2e.sh tests/e2e/project-visibility.spec.js`

### Steps

1. Use the same preview-safe scenario setup as Demo Media to reach an active company with a transaction-backed project and a transactionless project.
2. Capture a full-page screenshot of the Projects list after navigating broadly to the active project list state.
3. Capture a full-page screenshot of the new-invoice form after selecting the transactionless project.

### Full-Page Checkpoints

- `projects-list-transactionless-project`
- `invoice-form-transactionless-project-selected`

### Expected Comparisons

- Reviewers should see the Projects list preserve the existing page shell, filters, table styling, links, and monetary formatting while including a project that would previously have been omitted because it has no transaction totals.
- Reviewers should see the invoice form remain structurally unchanged while allowing the transactionless project to be selected.
- The visual comparison should focus on the stable page-level states, not exact row counts, generated setup text, or incidental DOM structure.

### Baseline SHA

`b6ad1a281db5ee0670144f413ce56360e481c917`


# Implementation Plan

1. Audit project list and selector queries, focusing on `view_projects`, `InvoiceForm`, customer/project detail contexts, and payment drawer project lists.
2. Remove the aggregate-total visibility gate from `view_projects` while preserving status filters, issuer scoping, date-filtered annotations, and sorting.
3. Implement company-scoped project-code uniqueness:
   - Recommended issuer-scope path: add a `Project.issuer` foreign key, backfill it from `project.customer.issuer`, remove `unique=True` from `project_code`, and add `UniqueConstraint(fields=["issuer", "project_code"])`.
   - If client/customer company scope is confirmed instead, use a `customer + project_code` constraint and skip the denormalized issuer field.
4. Keep the scoped company/issuer value synchronized when a project is created or its customer changes.
5. Add ProjectForm/model validation that reports duplicate scoped codes on `project_code` during add/edit flows.
6. Update admin/search/list filtering only as needed to reflect the scoped project model.
7. Add Django coverage for transactionless visibility, selector inclusion, active-company isolation, scoped uniqueness, and form validation.
8. Add the issue-specific Playwright scenario and screenshot checkpoints for reviewer evidence.

# Task List

- [x] Show transactionless projects in project surfaces
  - [x] Remove the invoice-total-based row filter from `view_projects`.
  - [x] Preserve active issuer scoping, project status filtering, date-filtered balance annotations, and ordering.
  - [x] Audit invoice/customer/payment project selector querysets and remove any transaction-dependent visibility filters found there.
  - [x] Add Django tests for Projects list visibility across transactionless, transaction-backed, date-filtered, and other-company cases.
  - [x] Add Django coverage for transactionless project availability in the new-invoice project field.

- [x] Scope project codes by company
  - [x] Replace global `Project.project_code` uniqueness with the chosen company-scoped schema constraint and migration backfill.
  - [x] Keep the project’s scope field synchronized from its customer when projects are created or edited.
  - [x] Add ProjectForm/model validation that rejects same-scope duplicate codes and excludes the current project on edit.
  - [x] Add tests proving cross-company duplicate codes are allowed and same-company duplicates are rejected.
  - [x] Update admin/model metadata where needed so project lookup remains practical after the schema change.

- [x] Add issue-bound Playwright evidence
  - [x] Add `tests/e2e/project-visibility.spec.js` with preview-safe setup for a transactionless project.
  - [x] Use the existing Playwright auth and screenshot helper patterns to capture the named full-page checkpoints.
  - [x] Keep screenshot capture focused on reviewer-visible states and leave strict uniqueness regression coverage in Django tests.

# Deployment / Rollout

A normal application deploy is sufficient, but this likely includes a database migration.

1. Run the standard build/deploy path with `python manage.py migrate`.
2. Confirm the migration backfills existing projects into the chosen company scope before applying the scoped uniqueness constraint.
3. No feature flag or environment change is required.
4. After deploy, verify a transactionless project appears in the Projects list and can be selected for a new invoice, and confirm duplicate project-code behavior in add/edit flows.

# File-Level Changes

## Add

- `invoices/migrations/0061_project_company_scoped_codes.py` — remove global project-code uniqueness, backfill scope, and add scoped uniqueness.
- `tests/e2e/project-visibility.spec.js` — issue-specific Playwright reviewer-evidence scenario.

## Modify

- `invoices/models.py` — update `Project` schema/validation/scope synchronization.
- `invoices/forms.py` — add scoped duplicate validation to `ProjectForm` and preserve invoice project selector behavior.
- `invoices/views.py` — remove transaction-total visibility filtering from `view_projects` and keep project queries issuer-scoped.
- `invoices/admin.py` — update project admin metadata if a denormalized issuer field is added.
- `invoices/tests/test_projects.py` — add ProjectForm and project view coverage.
- `invoices/tests/test_company.py` — update/add active-company project visibility coverage.
- `invoices/tests/test_invoices.py` — add or update invoice form selector coverage for transactionless projects.

## Keep

- `invoices/templates/invoices/view_projects.html` — no table redesign is expected.
- `invoices/templates/invoices/form_project.html` — existing field-error rendering should be reused.
- `invoices/templates/invoices/bulk_last_month.html` — bulk generation remains prior-invoice based.
- `scripts/e2e.sh`, `playwright.config.js`, and `tests/e2e/helpers/demo-evidence.js` — reuse the existing managed Playwright execution path.

# Open Questions

- Should project code uniqueness be scoped to the active issuing company/issuer, or to each client/customer company?
