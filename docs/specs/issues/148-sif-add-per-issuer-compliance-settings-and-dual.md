## Overview

Add the SIF / VERI*FACTU foundation for Spanish issuers in the multi-issuer invoices app. This issue should introduce issuer-scoped compliance settings, Spanish-only applicability, and first-class support for both `VERI_FACTU` and `NO_VERI_FACTU` modes without changing invoice issuance behavior yet.

## Problem

`Issuer` currently scopes companies, users, and invoice numbering, but there is no issuer-level SIF applicability, mode, AEAT environment, software metadata, certificate reference, deadline, or readiness state. Older planning text that described a `VERIFACTU_ONLY` foundation is now superseded: SIF applies only to Spanish issuers, and VERI*FACTU is optional.

## Proposed Outcome

- Add an issuer-scoped SIF settings model, preferably `IssuerSifSettings`, with a one-to-one relationship to `Issuer`.
- Persist:
  - explicit tax/establishment country, using `ES` as the Spanish applicability trigger
  - enabled flag
  - mode: `VERI_FACTU` or `NO_VERI_FACTU`
  - AEAT environment: test or production
  - taxpayer role and deadline category
  - software name, version, and code
  - certificate reference placeholder, not certificate secret material
  - operational/readiness status
- Add an applicability/readiness service future SIF issues can call before activating any SIF behavior.
- Extend the company/settings UI and Django admin so permitted users can view and edit SIF readiness for the active or otherwise accessible issuer.
- Ensure non-Spanish issuers remain on the existing normal invoice flow and do not receive Spanish SIF warnings or forced mode selection.
- Assumption: for this foundation, “valid Spanish tax identity” means a non-empty, syntactically valid Spanish NIF/NIE/CIF in the existing issuer company VAT/tax identifier field; AEAT certificate ownership and live taxpayer validation are deferred.

## Constraints / Non-Goals

- SIF applicability must be based on explicit issuer/establishment tax country, not customer country, invoice currency, or customer tax data.
- Do not use `VERIFACTU_ONLY`, `VERI*FACTU-only`, or any UI/model wording that marks `NO_VERI_FACTU` as unsupported.
- Do not implement AEAT XML generation, AEAT submission, submission queues, response parsing, QR generation, hash chains, immutable SIF records, event records, XAdES signatures, SIF exports, or invoice lifecycle changes in this issue.
- Do not store private certificate files, passwords, or secret material; only store a non-secret certificate reference/label.
- Do not make SIF settings global; every setting and readiness computation must be issuer-scoped.
- Do not force Spanish SIF behavior onto non-Spanish issuers.

## Acceptance Criteria

### User Outcome

1. A permitted user can view and edit SIF settings for the active issuer from company/settings.
2. A Spanish issuer can enable SIF and choose either `VERI_FACTU` or `NO_VERI_FACTU`.
3. The UI clearly states that VERI*FACTU is optional and that both modes are SIF modes with different downstream obligations.
4. The UI shows informational readiness deadlines for SL/corporate taxpayers (`2027-01-01`) and autónomo/other covered taxpayers (`2027-07-01`).
5. A non-Spanish issuer keeps the normal company settings experience without Spanish SIF warnings, forced AEAT fields, forced QR behavior, or forced mode selection.

### Technical Behavior

1. SIF settings are stored per issuer with a uniqueness guarantee and cannot bleed between issuers or companies.
2. Effective SIF activation returns true only when the issuer is explicitly Spanish, SIF is enabled, the Spanish tax identity is valid, and the settings are operationally ready.
3. The model persists both exact mode values: `VERI_FACTU` and `NO_VERI_FACTU`.
4. Form/model validation prevents enabling SIF for a non-Spanish issuer or for a Spanish issuer without a valid Spanish tax identifier.
5. Deadline date helpers derive the correct informational deadline from the selected taxpayer/deadline category.
6. Existing invoice creation, editing, PDF generation, and listing behavior remain unchanged in this issue.

### Operations / Deployment

1. The migration leaves existing issuers with SIF disabled and no effective SIF behavior until explicitly configured.
2. Production rollout requires only the database migration; no new scheduler, external service, certificate, or environment variable is required.
3. Admin surfaces allow staff to inspect issuer SIF applicability, mode, and readiness without exposing secret material.
4. Future issues #155 and #158 can depend on the settings and applicability service without introducing a new global SIF switch.

### Validation

1. Django tests cover model defaults, mode choices, deadline helpers, Spanish tax identity validation, and issuer isolation.
2. View/form tests cover permitted-user editing, cross-issuer access prevention, Spanish enablement, and non-Spanish guardrails.
3. Admin tests or assertions cover staff visibility of issuer SIF readiness fields.
4. Preview-safe Playwright evidence covers the Spanish issuer settings flow and the non-Spanish no-SIF-warning state.
5. The canonical validation path remains `python manage.py test` and `./scripts/ci.sh`.

## Implementation Plan

1. Add `IssuerSifSettings` in `invoices/models.py` with explicit choices/constants for country, mode, AEAT environment, taxpayer role, deadline category, and operational status.
2. Add a migration that creates the settings table and defaults all existing issuers to disabled/non-active SIF behavior.
3. Add a small SIF settings/applicability service, such as `invoices/services/sif.py`, to load settings, normalize/validate Spanish tax IDs, derive deadlines, and expose an effective activation result for future SIF issues.
4. Add an `IssuerSifSettingsForm` and integrate it into the existing `edit_company` transaction so company data, issuer settings, bank accounts, and SIF settings save atomically.
5. Update `company_settings.html` with a tax/SIF compliance section that shows country, mode, readiness, deadline, and missing prerequisites while keeping SIF warnings scoped to Spanish issuers only.
6. Update Django admin to expose SIF settings alongside issuers.
7. Add focused tests for model/service behavior, form validation, view permissions, issuer isolation, and template visibility.
8. Add issue-specific Playwright evidence support by registering new demo and visual validation identifiers in the repo-owned scripts.

## Task List

- [ ] Add issuer-scoped SIF settings and applicability logic
  - [ ] Add `IssuerSifSettings` choices, fields, computed deadline helpers, and model validation.
  - [ ] Add the migration with disabled/default-safe values for existing issuers.
  - [ ] Add a SIF service for settings lookup, Spanish tax ID normalization/validation, readiness, and effective activation.
  - [ ] Add model and service tests for defaults, both modes, deadlines, invalid identities, and issuer isolation.

- [ ] Integrate SIF settings into company and admin UI
  - [ ] Add an `IssuerSifSettingsForm` with Spanish-only enablement validation.
  - [ ] Update `edit_company` to create/load SIF settings for the target issuer and save them inside the existing transaction.
  - [ ] Add the company settings tax/SIF section with Spanish-only warnings and dual-mode controls.
  - [ ] Update Django admin list/detail surfaces for issuer SIF applicability and readiness.
  - [ ] Add view/form/template tests for permitted users, cross-issuer access prevention, Spanish enablement, and non-Spanish behavior.

- [ ] Add reviewer evidence and documentation hooks
  - [ ] Add a Playwright spec or extend an existing company-settings spec for Spanish SIF settings and non-Spanish guardrails.
  - [ ] Register `issuer-sif-settings-readiness` in `scripts/demo-evidence.sh`.
  - [ ] Register `issuer-sif-settings` in `scripts/visual-validation.sh`.
  - [ ] Document the Spanish-only, dual-mode foundation and explicitly note that AEAT streaming is #155 and non-VERI*FACTU local controls/XAdES are #158.

## Deployment / Rollout

- Apply the new Django migration before using SIF settings in production.
- Existing issuers remain SIF-disabled after deploy; operators must explicitly set issuer tax country to Spain and complete readiness fields before any future SIF feature can activate.
- No certificate files, AEAT credentials, background workers, or external connectivity are introduced in this issue.
- Rollback is a normal code/database rollback concern for the new settings table only; invoice data and existing invoice flows are not changed.

## Demo Media

### Scenario: issuer-sif-settings-readiness

#### Repo Command

./scripts/demo-evidence.sh issuer-sif-settings-readiness

#### Outputs

video + screenshots

#### Steps

1. Open the company settings page for a Spanish issuer in the preview app.
2. Configure the tax/SIF compliance section so SIF is enabled and the dual-mode choices are visible.
3. Save the settings and leave the Spanish issuer page showing the selected mode, deadline/readiness state, and Spanish-only prerequisites.
4. Open a non-Spanish issuer’s company settings page and leave it in the normal reviewer-visible state without Spanish SIF warnings or forced SIF mode selection.

#### Screenshot Checkpoints

- spanish-sif-readiness: full-page screenshot of the Spanish issuer settings page showing SIF readiness and dual-mode configuration
- non-spanish-normal-settings: full-page screenshot of the non-Spanish issuer settings page showing normal company settings without Spanish SIF warnings

## Visual Validation

### Identifier

issuer-sif-settings

### Capture Command

./scripts/visual-validation.sh issuer-sif-settings

### Steps

1. Open the company settings page for the seeded issuer data.
2. In baseline mode, capture stable pre-existing company settings pages only; do not assert PR-only SIF controls.
3. In current mode, open a Spanish issuer settings page and verify the PR-only tax/SIF compliance controls before capture.
4. In current mode, open a non-Spanish issuer settings page and verify the page does not show Spanish SIF warnings or forced mode controls before capture.

### Full-Page Checkpoints

- spanish-issuer-sif-settings: full-page screenshot of the company settings page with Spanish SIF readiness controls
- non-spanish-issuer-settings: full-page screenshot of a non-Spanish issuer settings page without Spanish SIF warnings

### Expected Comparisons

- The `spanish-issuer-sif-settings` baseline/current pair should show the added tax/SIF compliance section and dual-mode readiness controls without disrupting the existing general, finance, and invoice settings layout.
- The `non-spanish-issuer-settings` baseline/current pair should show that non-Spanish issuers keep a normal settings page and are not visually pushed into Spanish SIF compliance.

## File-Level Changes

### Add

- `invoices/services/sif.py`
- `invoices/migrations/0067_issuer_sif_settings.py`
- `invoices/tests/test_sif_settings.py`
- `tests/e2e/sif-settings.spec.js`
- Optional `docs/sif.md` for the Spanish-only dual-mode foundation summary

### Modify

- `invoices/models.py`
- `invoices/forms.py`
- `invoices/views.py`
- `invoices/admin.py`
- `invoices/templates/invoices/company_settings.html`
- `invoices/tests/test_company.py`
- `invoices/management/commands/seed_e2e_smoke.py`, only if preview evidence needs deterministic Spanish/non-Spanish issuer setup
- `scripts/demo-evidence.sh`
- `scripts/visual-validation.sh`
- `README.md`, only if a new SIF documentation page is added to the docs index

### Keep

- Invoice issuance, PDF, QR, hash, AEAT XML, AEAT SOAP, XAdES, export, and preservation flows unchanged.
- Managed workflow files unchanged unless evidence registration explicitly requires a repo-owned script update.
- `.env`, runtime databases, media, generated screenshots, and Playwright auth state untracked and unmodified.

## Open Questions

None.
