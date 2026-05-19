## Overview

Create a root-level `DESIGN.md` that documents the invoices app’s current UI design contract. This is a documentation-only task: the implementation should inspect the existing Django templates, CSS, static assets, and representative screenshots/evidence, then describe the current visual language without changing it.

The current app appears to use Pico.css and Charts.css as foundations, custom CSS tokens under `invoices/static/invoices/css/design/`, a light slate background, white surfaces, blue accent actions, mostly square controls, dense admin-style tables, a sticky/sidebar navigation shell, drawers for edit flows, and Tabler SVG icons. Existing docs screenshots may be useful as historical context, but current CSS/templates and rendered pages are the source of truth when they conflict.

## Problem

Future UI/UX automation does not have a single project-level source of truth for the invoices app’s visual language. Important styling rules are spread across CSS files, templates, partials, and older screenshots, which increases the risk that future agents invent new colors, spacing, typography, components, or interaction patterns.

## Proposed Outcome

Add `DESIGN.md` at the repository root with:

- YAML front matter containing practical tokens for colors, typography, spacing, rounded/border behavior, and core components.
- Markdown usage guidance describing how those tokens apply across dashboards, list pages, forms, drawers, navigation, filters, tables, feedback states, charts, and invoice PDFs.
- A conservative “current-state” description, not a redesign proposal.
- Explicit do/don’t rules for future UI agents, including the repo rules for Tabler Icons, Pico grouped controls, Charts.css charts, and consistent two-decimal monetary formatting.
- A `Visual Validation Guidance` section inside `DESIGN.md` explaining which future UI changes should use full-page screenshots versus focused captures.

Assumption: use the upstream-compatible `rounded` YAML token group rather than `radii`; document border/radius conventions in prose and component tokens.

## Constraints / Non-Goals

- Do not redesign the invoices UI.
- Do not change CSS, templates, JavaScript, Python behavior, migrations, package manifests, or screenshots unless a tiny documentation-support change is unavoidable.
- Do not add new UI components or migrate the app to a new design system.
- Do not make demo media or visual validation mandatory for this documentation-only issue.
- Do not inspect or document secrets, `.env` files, or credential-bearing environment files.
- Treat current committed UI code and rendered behavior as authoritative; use existing `docs/images/*` and `docs/gifs/*` only as secondary references.
- Keep the upstream `DESIGN.md` alpha status in mind: prefer lint-compatible, useful tokens over exhaustive modeling.

## Acceptance Criteria

### User Outcome

1. A root-level `DESIGN.md` exists and gives future agents a concise, reusable design contract for the invoices app.
2. The document describes the existing invoices UI and avoids aspirational redesign language.
3. The document includes explicit do/don’t rules that preserve the current visual language and repository UI conventions.

### Technical Behavior

1. YAML front matter starts and ends with `---`, includes `version: alpha`, `name`, practical `colors`, `typography`, `spacing`, `rounded`, and `components` tokens.
2. Color tokens use stable hex values inferred from existing CSS, not raw `color-mix()` expressions.
3. Token coverage includes the current background/surface/text/accent/border/success/danger/secondary/warning/chart colors where they can be inferred.
4. Typography, spacing, page width, density, borders, square-radius defaults, and intentional rounded exceptions are documented from current CSS/templates.
5. Markdown sections include at least `Overview`, `Colors`, `Typography`, `Layout And Density`, `Components`, `Interaction And States`, `Visual Validation Guidance`, and `Do's And Don'ts`.
6. Component guidance covers buttons, links, form fields, filter toggle groups, cards/surfaces, data tables, bulk toolbars, pagination, tabs, sidebar/company switcher, drawers/modals, alerts/messages, badges/status indicators, dashboard charts, and invoice PDF styling.
7. Existing app behavior and visual styling remain unchanged.

### Operations / Deployment

1. No database migrations, deployment steps, static asset rebuild requirements, or runtime configuration changes are introduced by this task.
2. No package dependency changes are made solely to run a one-off linter unless clearly justified.
3. The new design contract is safe to consume after merge by future automation, even if automation-side `DESIGN.md` support lands separately.

### Validation

1. `npx @google/design.md lint DESIGN.md` is run when feasible in the repo environment.
2. If the lint command cannot be run due to network, registry, or tool availability, the implementation notes the exact command attempted and the reason it could not complete.
3. The final change set is documentation-only unless the implementation explicitly explains any unavoidable support change.

## Implementation Plan

1. Inspect the current UI sources:
   - `invoices/static/invoices/css/design/tokens.css`
   - `invoices/static/invoices/css/design/components.css`
   - `invoices/static/invoices/css/base.css`
   - `invoices/static/invoices/css/navbar.css`
   - `invoices/static/invoices/css/render_invoice_pdf_styles.css`
   - Shared templates such as `base.html`, `navbar.html`, form/message/data-table partials, dashboard/list pages, expenses pages, drawer partials, company settings, and backup settings.
2. Review existing docs media as secondary context:
   - `docs/images/view_invoices.png`
   - `docs/images/form_invoices.png`
   - `docs/gifs/add_invoice.gif`
   - Treat these as historical if they conflict with current code or rendered behavior.
3. Draft `DESIGN.md` front matter:
   - Use lint-friendly YAML and valid hex colors.
   - Map current CSS variables to reusable semantic token names.
   - Include typography tokens for body, page heading, section title, table text, labels, captions/help text, and KPI values.
   - Include spacing tokens based on the existing 4px/8px/12px/16px/20px/24px/32px/40px scale.
   - Include `rounded` tokens that document the mostly square UI plus current intentional rounded exceptions.
   - Include component tokens for primary/secondary/danger actions, fields, surfaces, cards, badges, alerts, and table/filter patterns.
4. Draft the markdown body:
   - Describe the app’s current visual personality and density.
   - Explain semantic color usage and component behavior.
   - Document layout structure, responsive behavior, sidebar/topbar behavior, and table/card/drawer conventions.
   - Cover feedback states, empty states, errors, success messages, destructive actions, disabled/focus/hover states, and loading/status indicators.
   - Include invoice PDF/print styling as a customer-facing output style.
5. Add future guidance:
   - Write `Visual Validation Guidance` for future tasks, emphasizing full-page captures for page layout changes and focused captures only for details that full-page screenshots would hide.
   - Add concrete do/don’t rules, including Tabler icon usage, Pico grouped controls, Charts.css chart usage, and two-decimal money display.
6. Validate:
   - Run `npx @google/design.md lint DESIGN.md` if feasible.
   - Adjust YAML or section content for alpha-format compatibility without weakening the project-specific guidance.

## Task List

- [x] Derive the current design inventory
  - [x] Extract reusable color, spacing, typography, border, radius, and shadow values from the committed CSS files.
  - [x] Review representative templates for navigation, dashboards, lists, forms, drawers, tables, filters, messages, backups, expenses, and company settings.
  - [x] Review invoice PDF styling separately from the web app shell.
  - [x] Compare existing docs screenshots/GIFs against current code and avoid documenting outdated patterns as canonical.

- [x] Add the root `DESIGN.md` token contract
  - [x] Create `DESIGN.md` with alpha YAML front matter.
  - [x] Encode inferred colors, typography, spacing, rounded, and component tokens using lint-friendly values.
  - [x] Use token references for component colors and sizing where practical.
  - [x] Keep tokens descriptive but conservative so they reflect current reusable patterns.

- [x] Add the `DESIGN.md` usage guidance
  - [x] Write the overview, color, typography, layout/density, and component guidance sections.
  - [x] Document interaction and feedback states, including alerts, validation errors, empty states, status badges, destructive actions, and drawers.
  - [x] Add visual validation guidance for future UI work.
  - [x] Add do/don’t rules that preserve current app conventions.

- [x] Make the document lint-friendly and reviewable
  - [x] Adjust YAML and markdown for the alpha `DESIGN.md` format.
  - [x] Avoid committing package or runtime changes for a one-off lint run.
  - [x] Record the `npx @google/design.md lint DESIGN.md` result or the reason it could not be run.

## Deployment / Rollout

This is documentation-only. No deployment, migration, static collection, runtime configuration, preview, demo media, or visual validation rollout is required for this issue.

After merge, future UI automation can use `DESIGN.md` as project context. The file should not be treated as a mandate to run visual evidence for every future issue; it should guide future task-specific evidence decisions.

## File-Level Changes

- Add
  - `DESIGN.md`

- Modify
  - None expected.

- Keep
  - `invoices/static/invoices/css/design/tokens.css`
  - `invoices/static/invoices/css/design/components.css`
  - `invoices/static/invoices/css/base.css`
  - `invoices/static/invoices/css/navbar.css`
  - `invoices/static/invoices/css/render_invoice_pdf_styles.css`
  - Existing Django templates, JavaScript, Python code, tests, package manifests, and workflows.

## Open Questions

None.
