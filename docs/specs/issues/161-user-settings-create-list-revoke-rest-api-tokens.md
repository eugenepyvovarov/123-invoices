## Overview

Add a dedicated REST API token management area to User settings so authenticated users can create, list, and revoke their own `accounts.ApiToken` Bearer tokens for `/api/` without Django admin or management commands.

## Problem

REST API tokens already exist, but day-to-day lifecycle management is CLI/admin-only. User settings also has an existing “API key” area for the Expense import AI provider, which is unrelated to REST API Bearer tokens and can confuse operators.

## Proposed Outcome

Users can manage “Invoices API tokens” from `/accounts/user-settings/` in a clearly separate section. Token creation shows the plaintext token once in a copy-friendly state, while subsequent page views show only token metadata and prefix. Revocation is owner-scoped and uses the existing soft-revoke behavior.

## Constraints / Non-Goals

- Do not change the API authentication model, token hashing, token format, or account/issuer authorization behavior.
- Do not add company-bound token scopes or MCP-specific behavior.
- Do not remove or weaken the existing CLI commands or Django admin escape hatches.
- Do not expose plaintext secrets after the one-time creation reveal.
- Do not repurpose the Expense import AI provider API key UI; only clarify its copy if needed.
- Do not add token notes/scopes/editing unless they fall out naturally from existing fields; name and optional expiry are sufficient for this cut.

## Acceptance Criteria

### User Outcome

1. Authenticated users can create REST API tokens from User settings without shell or admin access.
2. Token creation requires a name and accepts an optional expiry.
3. The plaintext token is shown once immediately after creation in a copy-friendly UI.
4. Users can list their own token name, prefix, created time, last used time, expiry, and active/expired/revoked status.
5. Users can revoke their own tokens from the same settings area.
6. UI copy clearly distinguishes “Invoices API tokens” from the Expense import AI provider API key.

### Technical Behavior

1. Token creation uses `ApiToken.issue()` and stores only the hashed secret plus prefix in `ApiToken`.
2. Token revocation uses `ApiToken.revoke()` and scopes lookup to `request.user.api_tokens`.
3. Attempts to revoke another user’s token do not modify that token.
4. Token lists never include full plaintext secrets after the creation reveal.
5. Revoked and expired tokens cannot authenticate to `/api/`.
6. Existing CLI commands and `ApiTokenAdmin` remain available.

### Operations / Deployment

1. No model migration is expected unless implementation discovers an unavoidable schema need.
2. Existing tokens appear in the new UI as metadata-only rows; old plaintext secrets remain unrecoverable.
3. `docs/api.md` documents the User settings path and continues to document CLI/admin workflows as escape hatches.

### Validation

1. Django tests cover token creation, listing, one-time plaintext handling, owner-only visibility, owner-only revoke, and form validation.
2. API authentication tests cover revoked/expired token failure and confirm a UI-created token follows existing Bearer auth behavior.
3. Playwright evidence covers the visible create/list/revoke flow.
4. Visual validation captures the User settings page before/after the new token section.

## Implementation Plan

1. Add an `ApiTokenCreateForm` in `accounts/forms.py` with required `name` and optional `expires_at` validation.
2. Extend `accounts.views.user_settings` to:
   - query `request.user.api_tokens` for display,
   - handle `create_api_token` POSTs via `ApiToken.issue()`,
   - handle `revoke_api_token` POSTs via owner-scoped lookup and `revoke()`,
   - expose a transient one-time plaintext token reveal without persisting the secret in model data.
3. Update `accounts/templates/accounts/user_settings.html` with a dedicated “Invoices API tokens” section containing:
   - explanatory copy,
   - create form,
   - one-time token reveal state,
   - metadata list/table,
   - revoke controls for non-revoked tokens.
4. Keep the Expense import AI provider section intact and label it clearly as provider-specific, not REST API token management.
5. Update tests and docs around the new settings workflow.
6. Add issue-specific Playwright coverage and wire new demo/visual scenario identifiers into the repo scripts.

## Task List

- [x] Add API token form and User settings behavior
  - [x] Add a token creation form with required name and optional expiry parsing.
  - [x] Add owned-token query/context data for the User settings page.
  - [x] Add `create_api_token` POST handling using `ApiToken.issue()`.
  - [x] Add `revoke_api_token` POST handling using owner-scoped lookup and `ApiToken.revoke()`.
  - [x] Add focused Django tests for create/list/revoke, ownership, plaintext handling, and revoked auth.

- [ ] Update the User settings UI
  - [ ] Add a dedicated “Invoices API tokens” section separate from Expense import AI provider settings.
  - [ ] Render the create form, token metadata, status badges, and revoke controls with existing design patterns.
  - [ ] Render the one-time plaintext token reveal in a copy-friendly state.
  - [ ] Keep Expense import AI provider settings functional and clearly labeled.

- [ ] Update docs and evidence harness
  - [ ] Update `docs/api.md` with the User settings token workflow and retained CLI/admin options.
  - [ ] Add Playwright coverage for the visible create/list/revoke flow.
  - [ ] Add `api-token-settings-management` to `scripts/demo-evidence.sh`.
  - [ ] Add `api-token-settings` to `scripts/visual-validation.sh`.

## Deployment / Rollout

Deploy with the normal application release path. No data migration is expected. Existing API tokens remain valid unless revoked or expired, and existing CLI/admin workflows continue to work. After deployment, operators can use User settings for owner-managed token lifecycle tasks and reserve CLI/admin for administrative escape hatches.

## File-Level Changes

### Add

- `tests/e2e/api-token-settings.spec.js` for demo and visual evidence coverage.

### Modify

- `accounts/forms.py` to add the token creation form.
- `accounts/views.py` to add token listing, creation, and revocation handling.
- `accounts/templates/accounts/user_settings.html` to add the Invoices API token management UI.
- `accounts/tests/test_user_settings.py` to cover settings-page token behavior.
- `api/tests/test_authentication.py` if needed to connect UI-created/revoked tokens to Bearer auth assertions.
- `docs/api.md` to document the settings UX and CLI fallback.
- `scripts/demo-evidence.sh` to add the new demo scenario.
- `scripts/visual-validation.sh` to add the new visual validation identifier.

### Keep

- `accounts/models.py` token hashing/issue/revoke behavior unchanged unless implementation discovers a defect.
- Existing `issue_api_token`, `list_api_tokens`, `revoke_api_token`, and `ApiTokenAdmin` admin workflows.

## Demo Media

### Scenario: api-token-settings-management

#### Repo Command

./scripts/demo-evidence.sh api-token-settings-management

#### Outputs

video + screenshots

#### Steps

1. Log in with the seeded evidence user and open User settings.
2. Create a new Invoices API token through the visible settings form.
3. Capture the one-time plaintext token reveal and token metadata list.
4. Revoke the created token through the visible UI.
5. Leave User settings showing the token in a revoked/non-active state and the Expense import AI provider section as a separate feature.

#### Screenshot Checkpoints

- api-token-created: full-page screenshot of User settings after token creation with the one-time reveal and token metadata visible
- api-token-revoked: full-page screenshot of User settings after the created token is revoked

## Visual Validation

### Identifier

api-token-settings

### Capture Command

./scripts/visual-validation.sh api-token-settings

### Steps

1. Log in with the seeded evidence user and open `/accounts/user-settings/`.
2. In baseline mode, capture the existing User settings page as the fallback state where the new Invoices API tokens section is absent.
3. In current mode, open the same page and verify the dedicated Invoices API tokens section is visible and separate from the Expense import AI provider section before capture.
4. Capture the full User settings page.

### Full-Page Checkpoints

- user-settings-api-tokens: full-page screenshot of User settings including the existing settings sections and the new Invoices API token management area

### Expected Comparisons

- The `user-settings-api-tokens` baseline/current pair should show a new dedicated Invoices API token management section.
- The Expense import AI provider settings should remain visually separate and not appear repurposed as REST API token management.

## Open Questions

None.
