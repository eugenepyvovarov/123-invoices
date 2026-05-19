# Overview

The project edit flow should allow an existing project to remain editable even when its client has been deactivated. The immediate goal is to let users open a project tied to an inactive client, see that client in the form, and change the project status to inactive without needing to reactivate the client first.

# Problem

Today, `ProjectForm` limits the `customer` field to active customers only. When a project already belongs to an inactive customer, the edit form no longer includes that current customer in the select options. On `/projects/<id>/?tab=edit` and the standalone edit page, the user cannot see the selected client and may be blocked from saving unrelated changes such as setting the project itself to inactive.

# Proposed Outcome

Update project editing so the current customer is always present in the `customer` field queryset when editing an existing project, even if that customer is inactive. Keep new project creation behavior scoped to active customers only.

The recommended cut is:
- Preserve the current active-customer filter for new projects.
- When editing an existing project, append/include the project's assigned customer in the queryset if that customer is inactive.
- Make the inactive state visible in the option label so the form clearly communicates why the customer is normally unavailable.
- Keep project status changes independent from customer active status so a user can mark the project inactive and save successfully.

# Constraints / Non-Goals

- Do not change the `Customer` or `Project` data model.
- Do not bulk-expose all inactive customers in the project form.
- Do not change invoice project filtering or other flows that intentionally exclude inactive customers/projects.
- Do not require a migration.
- Do not add a new project-status workflow beyond fixing editability for already-linked projects.

# Acceptance Criteria

## User Outcome

1. When a user opens an existing project whose customer is inactive, the edit form still shows that customer as the selected value.
2. The user can change the project status to inactive and save without first reactivating the customer.
3. The customer option shown for an inactive linked client is clearly labeled as inactive.

## Technical Behavior

1. `ProjectForm` continues to list only active customers for new project creation.
2. `ProjectForm` includes the instance's current customer when editing an existing project, even if that customer has `is_active=False`.
3. The form does not expose unrelated inactive customers as selectable options.
4. Existing issuer scoping is preserved so only customers for the active issuer are included.

## Operations / Deployment

1. The change ships without schema changes or data backfills.
2. Existing project records linked to inactive customers remain editable after deployment.

## Validation

1. Automated tests cover the edit-form queryset behavior for a project tied to an inactive customer.
2. Automated tests cover successful project update submission when the linked customer is inactive.
3. Existing tests for excluding inactive customers from new-project creation remain valid or are added if currently missing.

# Implementation Plan

1. Refine `ProjectForm.__init__` so the base queryset still starts from active customers scoped to the issuer.
2. When the form is bound to an existing `Project` instance, add that instance's current customer to the queryset if needed.
3. Adjust the customer label rendering so inactive customers are distinguishable in the select field.
4. Verify both project edit entry points use the corrected form behavior.
5. Add regression coverage for form initialization and project update submission.

# Task List

- [x] Update project form queryset behavior
  - [x] Keep new-project customer choices limited to active customers for the current issuer
  - [x] Include the existing project's assigned customer in the queryset during edit mode when that customer is inactive
  - [x] Preserve issuer scoping and avoid exposing other inactive customers
  - [x] Mark inactive customer labels clearly in the form choice text

- [x] Validate edit flows that use `ProjectForm`
  - [x] Confirm the standalone project edit view uses the corrected queryset behavior
  - [x] Confirm the project detail edit tab uses the corrected queryset behavior
  - [x] Ensure saving a project with an inactive linked customer still succeeds when only project fields change

- [x] Add regression tests
  - [x] Add a form-level test proving an inactive linked customer appears for project edit
  - [x] Add a view-level test proving a project can be set inactive while its customer remains inactive
  - [x] Add or keep coverage proving inactive customers are still excluded for new project creation

# Deployment / Rollout

This is a low-risk application change with no migration or data rewrite. Rollout can happen with the normal deploy process.

Post-deploy validation should confirm:
- editing a project linked to an inactive customer shows the customer in the form
- saving the project as inactive succeeds from the project detail edit tab
- new project creation still omits inactive customers

# File-Level Changes

- Modify `invoices/forms.py` to adjust `ProjectForm` queryset construction and customer labeling
- Modify `invoices/tests.py` to add regression coverage for inactive-customer project edits
- Keep `invoices/views.py` unless testing shows view-specific handling is required
- Keep `invoices/templates/invoices/project_detail.html` unless a small UI hint is added for inactive customer labeling
- Keep `invoices/templates/invoices/form_project.html` unless a small UI hint is added for inactive customer labeling

# Open Questions

None.
