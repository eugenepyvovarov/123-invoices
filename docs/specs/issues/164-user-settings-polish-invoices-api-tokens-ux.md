## Overview

Polish the existing “Invoices API tokens” block on `/accounts/user-settings/` so it feels native to the surrounding User settings sections while preserving the create/list/revoke workflow introduced in invoices#161 / PR #162.

## Problem

The current token management block works functionally, but the UX reads as cramped and bolted on. The split create form plus token table inside one card has weak hierarchy, inconsistent spacing, awkward desktop proportions, and poor alignment compared with sibling settings sections such as Account, Companies, Security, and Expense import AI provider.

## Proposed Outcome

The Invoices API tokens area becomes a first-class User settings section with consistent card chrome, heading/help text hierarchy, spacing, form layout, list/table density, status presentation, action placement, and responsive behavior. The create form should be clear on desktop and stack above the token list on narrower widths. The token list should remain scannable by name, prefix, relevant dates, status, and revoke action, with an intentional empty state when no tokens exist.

Assumption: keep the existing owned-token list with status rows rather than adding an active-only filter, so users still get clear revoked/expired feedback after actions.

## Constraints / Non-Goals

- Do not change token hashing, token format, token authentication, ownership scoping, expiry semantics, or revoke behavior.
- Do not add token scopes, editing, filtering, pagination, MCP OAuth UX, or broader REST API management features.
- Do not redesign the entire User settings page or app shell.
- Do not repurpose the Expense import AI provider API key UI.
- Do not expose plaintext token secrets after the one-time creation reveal.
- Use existing `DESIGN.md` patterns, design tokens, table/form conventions, square controls, semantic badges, and Tabler icons only if icons are added.
- Keep the change focused on polish over new features.

## Acceptance Criteria

### User Outcome

1. The Invoices API tokens block visually matches sibling User settings sections in card treatment, headings, helper copy, spacing, and action rhythm.
2. The create-token flow is readable on desktop and stacks cleanly above the list on narrower widths without cramped columns or clipped controls.
3. The token list is easy to scan for token name, prefix, created/last-used/expiry dates, status, and revoke action.
4. The no-token state looks intentional and explains the next useful action instead of showing a broken or empty table.
5. The one-time secret reveal remains prominent, copy-friendly, and clearly tied to the newly created token.

### Technical Behavior

1. Existing create, list, revoke, and one-time plaintext reveal behavior remains functional.
2. Token listing remains scoped to `request.user.api_tokens`; other users’ tokens are not visible or revocable.
3. Revocation continues to use the existing soft-revoke behavior and only offers destructive action where appropriate.
4. Responsive token list markup preserves readable labels or equivalent context on narrow layouts.
5. Expense import AI provider settings remain visually separate and functionally unchanged.

### Operations / Deployment

1. No database migration is expected.
2. Existing API tokens remain valid, revoked, or expired according to their current stored state.
3. Static asset changes deploy through the normal application release path.
4. The PR summary briefly notes the UX changes made to the API tokens block.

### Validation

1. Existing Django tests for User settings API token behavior continue to pass and are updated only where UI copy/markup assertions intentionally change.
2. Regression coverage confirms create/list/revoke and one-time secret reveal still work.
3. Demo evidence captures the polished create/list/revoke flow and empty state.
4. Visual validation captures desktop and narrower User settings states for baseline/current comparison.

## Implementation Plan

1. Audit the current `accounts/templates/accounts/user_settings.html` token section against nearby User settings sections and `DESIGN.md`.
2. Refactor only the Invoices API tokens block markup to improve hierarchy, form/list separation, empty state, secret reveal placement, status/actions alignment, and responsive stacking.
3. Add small scoped CSS in the existing design component stylesheet only where existing utility/classes are insufficient.
4. Preserve existing form/view/model behavior; avoid backend changes unless a template regression exposes a real defect.
5. Update Django and Playwright assertions to match the polished UI without making brittle assertions about incidental DOM structure.
6. Reuse and update the existing API token demo and visual validation commands so reviewer evidence is tied to this polish pass.

## Task List

- [x] Rework the Invoices API token settings markup
  - [x] Align the section header, help text, and status badge treatment with sibling settings cards.
  - [x] Separate the create form and token list into a clearer responsive structure.
  - [x] Improve the one-time plaintext reveal placement and copy hierarchy without changing reveal semantics.
  - [x] Replace the empty table state with an intentional empty-state panel.
  - [x] Preserve accessible labels, form actions, CSRF handling, and existing stable test hooks where practical.

- [x] Add focused settings-page styling
  - [x] Add scoped component classes for the token block only where utilities are not enough.
  - [x] Use existing spacing, border, badge, table, and form design tokens from `DESIGN.md`.
  - [x] Ensure desktop layout avoids cramped columns and narrow layout stacks form above list.
  - [x] Keep destructive revoke actions visually distinct without overpowering routine settings actions.

- [x] Preserve behavior with tests
  - [x] Update `accounts/tests/test_user_settings.py` assertions for the polished empty state and token metadata presentation.
  - [x] Keep coverage for owner-scoped listing, create, one-time plaintext reveal, revoke, and revoked-token auth failure.
  - [x] Avoid changing `accounts.models.ApiToken` or authentication tests unless an existing regression is discovered.

- [ ] Update reviewer evidence harness
  - [ ] Reuse/update the existing `api-token-settings-management` demo scenario for empty/create/revoke evidence.
  - [ ] Reuse/update the existing `api-token-settings` visual validation identifier.
  - [ ] Add desktop and narrower-width visual checkpoints to `tests/e2e/api-token-settings.spec.js`.
  - [ ] Keep evidence setup in committed test/harness code, not product-only automation branches.

## Deployment / Rollout

Deploy through the normal application release path. This should be a template/static asset change with no migration and no token data conversion. Existing tokens and existing API clients should be unaffected. After deploy, validate the User settings page loads, token create/revoke still works, and the static assets are collected/served by the deployed build.

## File-Level Changes

### Add

- No new product files are required for the recommended cut.

### Modify

- `accounts/templates/accounts/user_settings.html` to polish the Invoices API tokens section markup.
- `invoices/static/invoices/css/design/components.css` for small scoped layout/style additions if existing utilities are insufficient.
- `accounts/tests/test_user_settings.py` to keep UI-facing token settings assertions aligned.
- `tests/e2e/api-token-settings.spec.js` to capture polished demo and visual validation states.

### Keep

- `accounts/models.py` token hashing, issue, expiry, and revoke behavior.
- `accounts/views.py` token create/list/revoke behavior unless a real UI integration defect requires a minimal adjustment.
- `accounts/forms.py` token form fields unless copy/placeholder polish is needed.
- `scripts/demo-evidence.sh` and `scripts/visual-validation.sh` scenario identifiers, reusing the existing API token commands.
- MCP OAuth, CLI token commands, Django admin token workflows, and Expense import AI provider behavior.

## Demo Media

### Scenario: api-token-settings-management

#### Repo Command

./scripts/demo-evidence.sh api-token-settings-management

#### Outputs

video + screenshots

#### Steps

1. Open User settings with the evidence user and show the polished Invoices API tokens empty state before creating a token.
2. Create an Invoices API token through the visible settings form.
3. Leave the one-time plaintext reveal and readable token metadata list visible.
4. Revoke the created token through the visible UI.
5. Leave User settings showing the revoked/non-active token state and the separate Expense import AI provider section.

#### Screenshot Checkpoints

- api-token-empty-state: full-page screenshot of User settings before token creation showing the intentional API tokens empty state
- api-token-created: full-page screenshot of User settings after token creation with the one-time reveal and token metadata visible
- api-token-revoked: full-page screenshot of User settings after the created token is revoked

## Visual Validation

### Identifier

api-token-settings

### Capture Command

./scripts/visual-validation.sh api-token-settings

### Steps

1. Open `/accounts/user-settings/` with the evidence user.
2. In baseline mode, capture the existing pre-polish User settings page and API tokens block without asserting PR-only selectors or layout classes.
3. In current mode, open the same page and verify the polished Invoices API tokens section is visible and separate from the Expense import AI provider section before capture.
4. Capture both desktop and narrower-width full-page states.

### Full-Page Checkpoints

- user-settings-api-tokens-desktop: full-page desktop screenshot of User settings including the Invoices API tokens section and surrounding settings sections
- user-settings-api-tokens-narrow: full-page narrower-width screenshot showing the token create form and list reflowed without cramped columns or clipped actions

### Expected Comparisons

- The `user-settings-api-tokens-desktop` baseline/current pair should show clearer card hierarchy, spacing, form/list separation, and status/action alignment.
- The `user-settings-api-tokens-narrow` baseline/current pair should show the token form stacking above the list and remaining readable on narrower widths.
- The Expense import AI provider section should remain visually separate from REST API token management.

## Open Questions

None.
