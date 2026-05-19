# Overview

Clarify the unified cross-company dashboard as a global, out-of-company view. When a user opens `/dashboard/cross-company/`, the company switcher should show `Dashboard` as the active selection and the sidebar should avoid showing company-scoped navigation or customer shortcuts that imply a specific company is selected.

# Problem

The unified dashboard currently inherits company-scoped sidebar state from the active company session. That creates two conflicting signals:

- the page content is global across companies
- the company switcher and sidebar still imply the user is inside one specific company

This is especially misleading when the previously selected company remains highlighted and company-scoped sidebar items remain visible.

# Proposed Outcome

On the unified dashboard:

- the company switcher trigger label shows `Dashboard`
- the `Dashboard` entry is the only active/current option in the switcher
- individual company entries remain available as switch targets, but none appear selected
- company-scoped sidebar navigation items and customer shortcut sections are hidden for this page

On normal company-scoped pages, existing company selection and sidebar behavior remain unchanged.

# Constraints / Non-Goals

- Do not change the stored `active_company_id` session value when viewing the unified dashboard.
- Do not change company-switch redirects or normal company-scoped navigation behavior.
- Do not redesign the sidebar or company switcher UI.
- Do not add new global navigation destinations beyond the existing unified dashboard entry.
- Do not expand this issue into broader cross-company navigation architecture.

# Acceptance Criteria

## User Outcome

1. On `/dashboard/cross-company/`, the company switcher visibly shows `Dashboard` as the active selection.
2. On `/dashboard/cross-company/`, no individual company option appears selected.
3. On `/dashboard/cross-company/`, company-scoped sidebar links and customer shortcut content are not shown.
4. On normal company-scoped pages, the active company and company-scoped sidebar content continue to render as they do today.

## Technical Behavior

1. Unified dashboard rendering uses page context to control switcher and sidebar state without mutating session-backed active company selection.
2. The `Dashboard` switcher entry remains linked to the unified dashboard route and is the only entry marked current on that page.
3. Company entries in the switcher remain available for switching away from the unified dashboard.
4. Sidebar suppression is limited to the unified dashboard view and does not alter sidebar behavior elsewhere.

## Operations / Deployment

1. The change ships without database migrations.
2. The change does not require feature flags or staged rollout controls.
3. Post-deploy verification can be completed through normal UI checks on one unified dashboard page and one company-scoped page.

## Validation

1. Automated regression coverage verifies the unified dashboard switcher label and active-item state.
2. Automated regression coverage verifies the unified dashboard does not render company-scoped sidebar navigation or customer shortcuts.
3. Automated regression coverage verifies a company-scoped page still renders the active company and company-scoped sidebar content.

# Implementation Plan

1. Update shared sidebar/company-switcher template logic to branch on `is_cross_company_dashboard`.
2. Render `Dashboard` as the active switcher label and current entry on the unified dashboard.
3. Suppress company-scoped sidebar navigation and sidebar customer sections when the unified dashboard flag is present.
4. Preserve all existing rendering paths for non-unified pages.
5. Add focused regression tests for both unified-dashboard and company-scoped behavior.

# Task List

- [x] Update unified dashboard switcher state
  - [x] Change the switcher trigger label to render `Dashboard` when `is_cross_company_dashboard` is true
  - [x] Mark only the `Dashboard` switcher entry as current on the unified dashboard
  - [x] Prevent individual company options from rendering selected state on the unified dashboard

- [x] Hide company-scoped sidebar content on the unified dashboard
  - [x] Suppress company-scoped sidebar navigation links when `is_cross_company_dashboard` is true
  - [x] Suppress desktop customer shortcut content when `is_cross_company_dashboard` is true
  - [x] Suppress mobile customer shortcut content when `is_cross_company_dashboard` is true

- [x] Add regression coverage
  - [x] Add a test asserting the unified dashboard switcher shows `Dashboard` and no selected company entry
  - [x] Add a test asserting the unified dashboard sidebar omits company-scoped links and customer shortcut content
  - [x] Add or extend a test asserting a normal company-scoped page still shows company-scoped sidebar content and the selected company

# Deployment / Rollout

- Ship as a normal application deploy.
- No schema, data, or configuration changes are required.
- After deploy, verify that `/dashboard/cross-company/` presents a global-only sidebar state and that a standard company page still shows company-scoped navigation.

# File-Level Changes

## Add

- None expected.

## Modify

- `invoices/templates/invoices/navbar.html` — branch switcher and sidebar rendering for unified-dashboard state
- `invoices/tests/test_company.py` — add regression coverage for unified-dashboard switcher and sidebar behavior

## Keep

- `invoices/views.py` — keep existing unified dashboard route and context contract unless a minimal context adjustment is required
- `invoices/context_processors.py` — keep active-company/session sourcing unchanged
- `invoices/utils/company_context.py` — keep active company persistence and switching logic unchanged

# Open Questions

None.
