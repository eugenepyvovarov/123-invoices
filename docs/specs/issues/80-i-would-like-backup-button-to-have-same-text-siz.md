# Overview

Update the superuser-only `Backups` action in the sidebar account area so it matches the adjacent `Logout` action in text size, icon treatment, and overall button presentation.

# Problem

The current account actions are visually inconsistent. `Backups` renders as plain linked text inside a button, while `Logout` already uses an icon-led button treatment. That mismatch makes the account area feel unfinished and makes the backup action look secondary even though it is a primary admin action.

# Proposed Outcome

Render `Backups` with the same account-action pattern as `Logout`, including:

- matching label size and weight
- a leading backup-related Tabler icon
- consistent spacing, alignment, and button height
- unchanged route, permissions, and behavior

# Constraints / Non-Goals

- Do not change superuser-only visibility for `Backups`.
- Do not change the `backup_settings` route or backup settings page behavior.
- Do not change logout behavior.
- Do not redesign the broader sidebar beyond the account-action consistency work needed here.
- Use Tabler Icons only.
- Prefer one shared sidebar account-action pattern instead of maintaining separate one-off markup.

# Acceptance Criteria

## User Outcome

1. Superusers see `Backups` with a leading icon and label sizing that visually matches `Logout`.
2. `Backups` and `Logout` appear as a consistent pair in the sidebar account section, including spacing, alignment, and button height.
3. Selecting `Backups` still opens the existing backup settings page.

## Technical Behavior

1. The sidebar account area uses one reusable action pattern for both `Backups` and `Logout`.
2. The `Backups` icon is a Tabler icon and the visible text label remains clear and accessible.
3. Existing superuser gating for `Backups` remains unchanged.

## Operations / Deployment

1. The change ships without migrations, new settings, or environment changes.
2. The implementation PR remains compatible with the managed `demo-evidence` workflow by using only the spec-declared Playwright command for proof.
3. The demo evidence for the implementation PR includes the recorded video and the named screenshot checkpoints from this spec.

## Validation

1. Server-side coverage verifies the superuser sidebar still renders the `Backups` action and that the rendered account action includes the icon-capable shared treatment.
2. A Playwright scenario validates the visible sidebar account state for a superuser and confirms navigation to backup settings.
3. Relevant existing tests continue to pass without regressing logout or backup-link visibility behavior.

# Demo Scenario

**Source-of-truth note:** Reuse is explicit for this issue. The implementation PR should use the scenario and command defined here for demo evidence unless this spec is intentionally updated.

- **Scenario ID:** `sidebar-backups-account-action`
- **Command:** `./scripts/e2e.sh tests/e2e/sidebar-backups-account-action.spec.js`
- **User-visible steps:**
  1. Seed the repo-owned E2E data and open the app with the standard Playwright login flow.
  2. Sign in and land on the dashboard with the sidebar visible.
  3. Move to the `Account` section in the sidebar.
  4. Confirm `Backups` shows a leading backup-related icon and visually matches the `Logout` action’s text size and button treatment.
  5. Select `Backups` and confirm the existing backup settings page opens.
- **Screenshot checkpoints:**
  - `account-sidebar-actions`
  - `account-sidebar-backups-matches-logout`
  - `backup-settings-destination`
- **Recorded evidence:**
  - The same spec-declared command must be the path used by the managed demo workflow to attach the scenario video plus the named screenshots to the PR.

# Implementation Plan

1. Update `invoices/templates/invoices/navbar.html` so `Backups` follows the same icon-plus-label action structure as `Logout`.
2. Add or adjust scoped sidebar account-action styling only where needed to keep icon spacing, text sizing, and alignment consistent.
3. Choose a backup-related Tabler icon that fits the existing sidebar icon scale.
4. Extend server-side coverage for the superuser sidebar account action.
5. Add the spec-bound Playwright scenario for the superuser sidebar account state and backup-settings navigation.

# Task List

- [x] Unify the sidebar account action markup
  - [x] Refactor the account action markup so `Backups` and `Logout` use the same structure.
  - [x] Add a backup-related Tabler icon to the `Backups` action.
  - [x] Preserve the existing `backup_settings` destination and logout form submission behavior.

- [x] Align the sidebar account action presentation
  - [x] Add or adjust scoped sidebar styles so both account actions share text size, spacing, alignment, and button height.
  - [x] Verify the chosen backup icon matches the existing icon scale used by the logout action.

- [x] Add regression coverage and demo proof
  - [x] Update the server-side backup/sidebar test to assert the shared icon-capable account action treatment for superusers.
  - [x] Add `tests/e2e/sidebar-backups-account-action.spec.js` for the spec-defined superuser sidebar flow.
  - [x] Capture the named screenshot checkpoints from the Playwright scenario and keep the spec-declared command as the PR demo-evidence path.

# Deployment / Rollout

This is a low-risk UI-only change with no migration or feature-flag work.

Rollout should follow the normal deploy path for template and static updates. Validation after deployment should include checking the sidebar account section in a superuser session, confirming `Backups` still routes to backup settings, and confirming the implementation PR’s demo evidence includes the recorded video and named screenshots from the spec-defined Playwright command.

# File-Level Changes

- **Modify** `invoices/templates/invoices/navbar.html` — normalize the account-action markup for `Backups` and `Logout`.
- **Modify** `invoices/static/invoices/css/navbar.css` — add or adjust scoped sidebar account-action styling if needed.
- **Modify** `invoices/tests/test_backups.py` — extend sidebar assertions to cover the updated rendered treatment.
- **Add** `tests/e2e/sidebar-backups-account-action.spec.js` — define the spec-bound Playwright demo scenario for this UI change.
- **Keep** `playwright.config.js` — reuse the existing Playwright project and artifact flow unless the spec-defined command cannot emit the required demo evidence without a targeted adjustment.
- **Keep** `invoices/views.py` and `invoices/urls.py` — no route or permission changes are expected.

# Open Questions

None.
