## Overview

Create a small User settings integration hub with two related tabs: **API** for existing REST Bearer token management and **MCP** for human-readable MCP connection guidance. Keep REST tokens and MCP OAuth distinct while making both discoverable from the same settings area.

## Problem

User settings already exposes Invoices REST API token lifecycle controls, but MCP onboarding lives only in docs/runtime behavior. Users and agents have no obvious place to find the deployment’s MCP endpoint, OAuth expectations, or whether the instance is configured for MCP. Without a grouped settings surface, REST API tokens and MCP OAuth can also be confused.

## Proposed Outcome

- User settings contains one integration section with **API** and **MCP** tabs.
- The **API** tab hosts the existing Invoices API token create/list/revoke UI without changing token semantics.
- The **MCP** tab shows:
  - a short plain-language explanation of MCP in this app,
  - the configured Streamable HTTP MCP endpoint/resource URL with a copy action,
  - non-secret OAuth/CIMD/pre-registered-client guidance for Hermes, Codex, and generic MCP clients,
  - a status badge/notice derived from non-secret web-side MCP configuration,
  - supported scopes and discovery/auth URLs only where useful for setup.
- The first slice reports MCP configuration/readiness only; it does not perform live service health checks or add OAuth client/consent management.

## Constraints / Non-Goals

- Do not replace REST API Bearer tokens with MCP credentials.
- Do not change the MCP security model shipped by #143/PR #163.
- Do not expose `INVOICES_MCP_API_TOKEN`, OAuth access/refresh tokens, client secrets, Authorization headers, or other runtime secrets in HTML, JavaScript, logs, screenshots, or docs examples.
- Do not add connected OAuth client listing, consent revocation, enterprise IdP admin UI, DCR management, or first-party client metadata publishing in this slice.
- Do not dump raw protocol docs into the page; keep the MCP tab actionable and concise.
- Do not add live MCP health polling to the settings page; use deployment configuration status and leave runtime probing to deploy verification.
- Preserve the current settings visual language and tab patterns from `DESIGN.md`.

## Acceptance Criteria

### User Outcome

1. Authenticated users can open User settings and see one clear integration area with **API** and **MCP** tabs.
2. The **API** tab contains the existing REST API token management workflow, including one-time plaintext reveal on creation and owner-scoped revocation.
3. The **MCP** tab shows a copyable deployment-specific MCP endpoint/resource URL and clearly labels whether MCP appears configured for this instance.
4. The **MCP** tab explains OAuth 2.1 + PKCE, CIMD URL client IDs, and pre-registered clients in plain language suitable for Hermes, Codex, and generic Streamable HTTP MCP clients.
5. Narrow/mobile layouts keep the integration tabs usable without broken overflow or hidden controls.

### Technical Behavior

1. MCP display data is built from non-secret Django settings such as `MCP_OAUTH_RESOURCE_URL`, `MCP_OAUTH_ISSUER_URL`, `MCP_OAUTH_CIMD_ENABLED`, and OAuth scope metadata.
2. The UI never reads or renders upstream MCP API tokens, OAuth access/refresh tokens, client secrets, or saved provider API keys.
3. Tab switching works for both the new integration tabs and the existing Security tabs without one tab group affecting another.
4. Tabs and panels include accessible state such as active styling, `aria-selected`, `aria-controls`, and keyboard-visible focus.
5. Copy buttons only copy public/non-secret values and degrade safely if the Clipboard API is unavailable.

### Operations / Deployment

1. No database migration is expected.
2. Existing REST API tokens remain valid and keep their existing lifecycle behavior.
3. Production deployments must keep web-side `MCP_OAUTH_ISSUER_URL` and `MCP_OAUTH_RESOURCE_URL` aligned with the public HTTPS MCP/OAuth routes.
4. If MCP is not publicly configured, the MCP tab shows a disabled/not-ready status instead of presenting a localhost/default URL as production-ready.

### Validation

1. Django tests cover rendering the integration tabs, MCP connection context, configuration status, and secret redaction.
2. Existing API token view tests continue to cover create/list/revoke behavior after the UI moves under the API tab.
3. Playwright coverage verifies tab switching, copy control visibility, and a narrow viewport for the integration hub.
4. `python manage.py test` and the repo-owned E2E/evidence commands for this issue pass.

## Implementation Plan

1. Add a small non-secret MCP settings/context helper for User settings.
   - Source endpoint/resource from `settings.MCP_OAUTH_RESOURCE_URL`.
   - Source issuer/auth metadata from `settings.MCP_OAUTH_ISSUER_URL`, well-known route names, and OAuth scopes.
   - Mark status as configured only when the endpoint is usable for the current deployment; avoid presenting local/default values as public-ready in non-debug contexts.
2. Refactor `accounts/templates/accounts/user_settings.html` so the REST API token UI moves into an **API** tab inside a new integrations section.
3. Add the **MCP** tab with status, copyable endpoint, concise setup steps, scope notes, and placeholder-safe Hermes/Codex/generic client guidance.
4. Generalize the settings tab JavaScript so multiple tab groups can coexist, update ARIA state, and support copy buttons for both API token reveal and MCP public values.
5. Add or adjust component CSS only as needed for responsive tab wrapping/scrolling and copyable endpoint rows.
6. Update tests and documentation to reflect that REST tokens and MCP connection setup now live in the User settings integration hub.
7. Add issue-specific demo and visual-validation script routes for the new integration tabs.

## Task List

- [x] Add MCP connection context for User settings
  - [x] Build a non-secret helper that normalizes endpoint/resource, issuer, metadata URLs, CIMD availability, and scopes.
  - [x] Define configured/not-configured/local-development status copy without performing a live MCP probe.
  - [x] Add Django tests for configured and not-publicly-configured MCP display states.
  - [x] Add tests proving secret-like settings are not rendered in the settings response.

- [x] Build the API/MCP integration tabs
  - [x] Wrap the existing Invoices API token UI in the **API** tab without changing POST actions or token lifecycle behavior.
  - [x] Add the **MCP** tab content with copyable endpoint and concise client onboarding guidance.
  - [x] Ensure the Expense import AI provider section remains separate and not framed as REST or MCP credential management.
  - [x] Add/update template tests for tab labels, panels, MCP status, and existing API token controls.

- [x] Harden tab and copy interactions
  - [x] Replace the single-container tab initializer with a reusable initializer for all settings tab groups.
  - [x] Update active classes and ARIA attributes on tab switch.
  - [x] Add copy-button handling for public MCP values without interfering with the API token one-time copy action.
  - [x] Add Playwright coverage for desktop and narrow/mobile tab switching.

- [ ] Update docs and reviewer evidence harness
  - [ ] Update `docs/api.md` and `docs/mcp-server.md` to point users to the new User settings integration hub where appropriate.
  - [ ] Add a Playwright evidence spec for the API/MCP tab flow.
  - [ ] Add `user-settings-api-mcp-tabs` routes to demo and visual-validation scripts.

## Deployment / Rollout

Deploy through the normal application release path. No data migration is expected. If static JavaScript/CSS changes are added, they roll out with the existing static asset path.

Before production rollout, confirm web-side `MCP_OAUTH_ISSUER_URL` and `MCP_OAUTH_RESOURCE_URL` are public HTTPS values matching the MCP service configuration. The page should show a not-ready/local status when those values are absent or only local defaults. Continue using `scripts/verify_deploy.sh` and `scripts/mcp_probe.py` for actual MCP service verification; the settings UI is not a health-check replacement.

## File-Level Changes

### Add

- `accounts/mcp_settings.py` for non-secret MCP display/context helpers.
- `tests/e2e/user-settings-integrations.spec.js` for API/MCP tab and evidence coverage.

### Modify

- `accounts/views.py` to include MCP connection context in User settings.
- `accounts/templates/accounts/user_settings.html` to add the integrations tab section and MCP tab content.
- `accounts/tests/test_user_settings.py` to cover the new tab layout, MCP context, and secret redaction.
- `invoices/static/invoices/css/design/components.css` only if responsive tab/copy-row styling needs small shared additions.
- `invoices/static/invoices/js/` or the User settings inline script to support reusable tabs and public-value copy buttons.
- `tests/e2e/api-token-settings.spec.js` if existing API token evidence needs selector updates after the tab refactor.
- `scripts/demo-evidence.sh` and `scripts/visual-validation.sh` to register the new issue-specific scenario/identifier.
- `docs/api.md` and `docs/mcp-server.md` for user-facing setup references.

### Keep

- `accounts.models.ApiToken` schema and token hashing/revocation behavior.
- `mcp_oauth/` and `invoices_mcp/` auth/security behavior except for read-only display references.
- Existing Expense import AI provider storage and masking behavior.
- Managed workflow files and runtime secret files unchanged.

## Demo Media

### Scenario: user-settings-api-mcp-tabs

#### Repo Command

./scripts/demo-evidence.sh user-settings-api-mcp-tabs

#### Outputs

video + screenshots

#### Steps

1. Log in with the seeded reviewer user and open User settings.
2. Open the integration area with the API tab active and show the REST token management controls in their new tabbed location.
3. Switch to the MCP tab, use the visible endpoint copy action, and leave the MCP connection guidance visible.
4. Leave User settings in a reviewer-visible state that shows REST and MCP are separate integration paths.

#### Screenshot Checkpoints

- integrations-api-tab: full-page screenshot of User settings with the API tab active in the integration hub
- integrations-mcp-tab: full-page screenshot of User settings with the MCP tab active, including endpoint/status and onboarding guidance

## Visual Validation

### Identifier

user-settings-api-mcp-tabs

### Capture Command

./scripts/visual-validation.sh user-settings-api-mcp-tabs

### Steps

1. Log in with the seeded reviewer user and open `/accounts/user-settings/`.
2. In baseline mode, capture the existing User settings page as the fallback state because the new API/MCP integration tabs are absent.
3. In current mode, capture the integration hub with the API tab active.
4. In current mode, switch to the MCP tab and capture the reviewer-visible MCP connection block.
5. Repeat the MCP-tab capture at a narrow mobile viewport to show the tabs and copyable endpoint remain usable.

### Full-Page Checkpoints

- integrations-api-tab-desktop: full-page desktop screenshot of User settings with the API tab active
- integrations-mcp-tab-desktop: full-page desktop screenshot of User settings with the MCP tab active
- integrations-mcp-tab-mobile: full-page narrow-viewport screenshot of User settings with the MCP tab active

### Expected Comparisons

- The `integrations-api-tab-desktop` baseline/current pair should show the REST token controls moved into a clear API tab within one integration hub.
- The `integrations-mcp-tab-desktop` baseline/current pair should show a new MCP connection block with status, endpoint, and concise onboarding guidance.
- The `integrations-mcp-tab-mobile` baseline/current pair should show the integration tabs and MCP endpoint/copy area remain usable on a narrow viewport.

## Open Questions

None.
