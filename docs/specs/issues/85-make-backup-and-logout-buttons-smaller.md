# Overview

Make the sidebar `Backups` and `Logout` account actions visually smaller by reducing their shared text size and internal padding. Keep the change narrow to the account section of the managed web UI.

# Problem

The buttons currently use the shared sidebar account-action treatment added for the earlier backup/logout alignment work, but that treatment is still oversized for the sidebar context. In `invoices/static/invoices/css/navbar.css`, the account actions currently use `min-height: 4.25rem`, `padding: 0.85rem 1.2rem`, and `1rem` label text, which makes the account section feel heavier than the surrounding navigation. The issue request is specifically to make the text and in-button spacing smaller.

# Proposed Outcome

Apply a smaller shared sidebar account-action size to both `Backups` and `Logout` so they remain full-width, icon-led, and visually matched, but with less text size and less whitespace inside the buttons.

The recommended cut is CSS-first: shrink the existing shared `.sidebar__account-action` treatment rather than introducing separate per-button markup or behavior changes.

# Constraints / Non-Goals

- Scope is limited to the `Account` section actions in the sidebar.
- Do not change the `Backups` route, superuser gating, or backup settings page behavior.
- Do not change logout submission behavior.
- Do not restyle the main sidebar navigation, company switcher, or buttons inside `invoices/templates/invoices/backup_settings.html`.
- Prefer one shared compact account-action treatment over button-specific overrides.
- Do not add migrations, settings changes, or environment changes.

# Acceptance Criteria

## User Outcome

1. In the sidebar account section, `Backups` and `Logout` render with visibly smaller label text and tighter internal padding than the current large-button treatment.
2. `Backups` and `Logout` still appear as a matched pair with aligned icons, labels, full-width layout, and consistent button styling.
3. Selecting `Backups` still opens the existing backup settings page, and `Logout` still behaves as the existing logout action.

## Technical Behavior

1. Both actions continue to share one sidebar account-action sizing pattern rather than separate button-specific styles.
2. The compact styling is implemented in the sidebar-specific styling layer so other sidebar links and backup-settings page buttons do not accidentally inherit it.
3. The existing superuser-only visibility for `Backups` remains unchanged.
4. The compact treatment keeps the icon-plus-label layout readable and aligned within the current sidebar width.

## Operations / Deployment

1. The change ships without migrations, feature flags, or environment/config updates.
2. Deployment follows the normal template/static-asset path and picks up the updated sidebar CSS through the existing build and collectstatic flow.
3. The implementation PR uses the spec-declared Playwright command for demo evidence.

## Validation

1. The reused Playwright sidebar account-action scenario verifies that `Backups` and `Logout` still share matching computed styles after the size reduction and that `Backups` still navigates to backup settings.
2. Relevant existing Django backup/sidebar render coverage continues to pass without route or permission regressions.
3. Demo evidence includes the named screenshot checkpoints from this spec so reviewers can visually confirm the smaller button treatment.

# Demo Scenario

**Source-of-truth note:** Reuse is explicit for this issue. Update and reuse the existing sidebar account-action Playwright path below; do not treat older repo history as automatic proof for this task.

- **Scenario ID:** `sidebar-account-actions-compact`
- **Command:** `./scripts/e2e.sh tests/e2e/sidebar-backups-account-action.spec.js`
- **User-visible steps:**
  1. Seed the repo-owned E2E smoke data and open the app with the standard Playwright login flow.
  2. Sign in as a superuser and land on the dashboard with the sidebar visible.
  3. Move to the `Account` section in the sidebar.
  4. Confirm `Backups` and `Logout` render with smaller text and tighter padding while remaining aligned and full-width.
  5. Select `Backups` and confirm the existing backup settings page opens.
- **Screenshot checkpoints:**
  - `account-sidebar-actions-compact`
  - `account-sidebar-buttons-aligned`
  - `backup-settings-destination`
- **Recorded evidence:**
  - The same spec-declared command must be the path used by the managed demo workflow to attach the scenario video and named screenshots to the implementation PR.

# Implementation Plan

1. Reduce the shared `.sidebar__account-action` size in `invoices/static/invoices/css/navbar.css` by lowering label sizing and internal padding from the current oversized sidebar treatment while preserving the existing icon-and-label layout.
2. Keep the current shared `Backups`/`Logout` markup in `invoices/templates/invoices/navbar.html`; only add a single scoping hook if it is strictly necessary to keep the change isolated.
3. Update `tests/e2e/sidebar-backups-account-action.spec.js` to assert the compact computed styles for both actions and capture the spec-defined screenshot checkpoints.
4. Re-run the relevant Django and Playwright validation paths to confirm the UI size reduction does not regress backup visibility, navigation, or logout behavior.

# Task List

- [x] Compact the shared sidebar account-action treatment
  - [x] Reduce `.sidebar__account-action` padding in `invoices/static/invoices/css/navbar.css`.
  - [x] Reduce the shared account-action label size and overall button height/min-height in the same CSS file.
  - [x] Verify the existing icon alignment and full-width layout still hold for both `Backups` and `Logout`.
  - [x] Update `tests/e2e/sidebar-backups-account-action.spec.js` to assert the smaller shared computed styles for the two account actions.

- [x] Refresh demo evidence for the compact sidebar state
  - [x] Capture the `account-sidebar-actions-compact` checkpoint from the reused sidebar scenario.
  - [x] Capture the `account-sidebar-buttons-aligned` checkpoint from the reused sidebar scenario.
  - [x] Preserve the `backup-settings-destination` checkpoint after navigating through `Backups`.

# Deployment / Rollout

This is a low-risk UI-only change.

Rollout should use the normal deploy path for template and static asset updates. Post-deploy validation should use a superuser session to confirm the sidebar `Backups` and `Logout` actions are smaller, remain aligned, and still route or submit exactly as before. Review evidence should come from the spec-defined Playwright command and named checkpoints.

# File-Level Changes

## Add

- None.

## Modify

- `invoices/static/invoices/css/navbar.css` — reduce the shared `Backups`/`Logout` account-action padding, label size, and overall button footprint.
- `tests/e2e/sidebar-backups-account-action.spec.js` — explicitly reuse and update the existing sidebar scenario to validate the compact treatment and required checkpoints.

## Keep

- `invoices/templates/invoices/navbar.html` — the existing shared account-action markup already covers the requested scope.
- `invoices/templates/invoices/backup_settings.html` — no backup settings page button or layout changes are part of this issue.
- `invoices/tests/test_backups.py` — existing render and permission coverage should remain applicable because the recommended cut avoids markup or route changes.
- `scripts/e2e.sh` and `playwright.config.js` — reuse the current Playwright runner/config for the spec-defined command.

# Open Questions

None.
