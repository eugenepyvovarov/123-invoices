## Overview

Build an incoming invoice inbox for supplier invoices and receipts. The inbox stages IMAP-fetched email candidates for review, suggests the correct issuer/company, stores candidate artifacts, and creates accounting records only after a user confirms the company and selected file.

This draft recommends an IMAP-only, review-first MVP focused on converting paid incoming invoices into existing `Expense` records. Unpaid supplier-bill handling and first-class expense currency remain scope decisions in `Open Questions`.

## Problem

Supplier invoices currently have no safe intake workflow. The existing `Invoice` model represents outgoing customer invoices, while `Expense` can store paid supplier costs but requires `paid_date`. Blindly creating records from fetched email would risk incorrect company routing, duplicate expenses, and loss of source provenance.

## Proposed Outcome

- Add incoming email source, issuer routing rule, candidate, and artifact models without overloading outgoing invoices.
- Connect one configured IMAP mailbox source and poll it manually/non-destructively.
- Store candidates idempotently before any accounting record is created.
- Save invoice-looking attachments and generate an email-body PDF artifact when no suitable attachment exists.
- Suggest an issuer using recipient/delivered-to aliases, legal names, VAT/tax identifiers, keywords, and extracted candidate text.
- Keep uncertain candidates in review states; never auto-convert fetched email.
- Add inbox list/detail/review UI with filters, artifact previews/downloads, detection reasons, duplicate warnings, company override, and review actions.
- Convert paid reviewed candidates into `Expense` records linked back to the source candidate and selected artifact.
- Keep rejected, duplicate, and needs-fetch candidates in history.
- Use synthetic email fixtures for tests, demo media, and visual validation; do not require real mailbox credentials for reviewer evidence.

## Constraints / Non-Goals

- Do not change existing outgoing `Invoice` semantics.
- Do not add Gmail OAuth/API support in this issue; mailbox connection is IMAP only.
- Do not implement vendor-portal browser automation.
- Do not scrape broad personal mailboxes; polling must use configured folder/search scope.
- Do not delete, archive, label, or mark source emails as handled in this first version.
- Do not add scheduled polling until the manual workflow is stable.
- Do not store real IMAP credentials, passwords, cookies, source messages, or customer data in git, logs, markdown, screenshots, or fixtures.
- Do not make OCR mandatory unless existing dependencies make it trivial and deterministic.
- Do not add a full supplier-bill/AP ledger unless the unpaid-bill open question is answered that it is required for this issue.
- Keep existing expense statement import behavior company-scoped and unchanged.

## Acceptance Criteria

### User Outcome

1. A permitted user can open an incoming invoice inbox from app navigation and view staged candidates by status, company, source, confidence, date, and missing-review filters.
2. A user can configure or seed one IMAP invoice email source without entering secrets into committed files or reviewer evidence.
3. A manual poll/import action creates candidates without creating expenses or bills.
4. A candidate detail page shows sender, subject, received date, suggested company, status, artifacts, extraction hints, detection reasons, warnings, and review actions.
5. The user can confirm or override the company before conversion.
6. The user can choose an attached PDF, generated email-body PDF, or another stored artifact as the final expense attachment.
7. A paid reviewed candidate can be converted into an `Expense` for the confirmed issuer with the selected artifact attached.
8. Rejected, not-invoice, duplicate, and needs-fetch candidates remain visible in history and are not converted.
9. Unclear company matches remain in `needs_review` and are not auto-converted.

### Technical Behavior

1. New incoming models are issuer-aware and enforce existing user/issuer access boundaries.
2. `IncomingEmailSource` supports IMAP source metadata, enabled state, folder/search scope, cursor state, and credential references only; raw secrets are not exposed in logs or screenshots.
3. `IssuerEmailRoutingRule` stores per-issuer aliases, delivered-to addresses, legal names, VAT/tax identifiers, keywords, and confidence threshold settings.
4. `IncomingInvoiceCandidate` is unique per source and provider message id and stores sanitized headers/body/provider metadata, detection metadata, duplicate metadata, status, suggested/resolved issuer, and linked converted expense.
5. `IncomingInvoiceArtifact` stores each attachment/body artifact under `media/`, records content type, size, SHA-256 hash, extracted text when available, parsed metadata, and invoice-likeness confidence.
6. Polling is non-destructive, idempotent, limited to configured IMAP scope, and safe to rerun.
7. Email-body PDFs are generated with existing PDF tooling when no suitable attachment exists, and both body PDFs and useful attachments are retained when both exist.
8. Portal-link-only candidates with no usable file/body invoice are marked `needs_fetch`.
9. Routing chooses a suggested issuer only when exactly one issuer meets confidence requirements; otherwise the candidate stays `needs_review`.
10. Duplicate detection covers source/message id, artifact SHA-256, candidate invoice fingerprints, and incoming-created expense provenance; conversion of duplicates requires explicit override or link-existing action.
11. Conversion requires confirmed issuer, selected artifact, paid status, paid date, amount, and description/vendor confirmation before creating an `Expense`.
12. Created expenses include incoming-invoice provenance in `raw_data`, and dashboard/cache state is invalidated after conversion.

### Operations / Deployment

1. The change includes database migrations for new incoming source/routing/candidate/artifact tables.
2. Runtime artifacts are stored under `media/` and are not committed.
3. Mailbox polling is manual only through a repo-owned management command in this issue.
4. Documentation describes IMAP source setup, credential-reference expectations, fixture import, poll command usage, review workflow, and security/privacy rules.
5. Rollback is a normal code rollback; already-created incoming tables/media may remain inert unless an operator chooses separate cleanup.

### Validation

1. Django tests cover model constraints, upload paths, status transitions, idempotent polling/import, artifact hashing, email-body PDF generation, company routing, duplicate detection, review actions, conversion to `Expense`, issuer access scoping, and dashboard cache invalidation.
2. View/form tests cover inbox filters, candidate detail, company override, artifact selection, reject/not-invoice/needs-fetch actions, duplicate override/link-existing handling, and conversion validation.
3. Synthetic fixtures cover attached-PDF email, no-attachment body-PDF email, ambiguous-company email, portal-link-only email, duplicate message id, and duplicate file hash.
4. Existing outgoing invoice tests and existing expense import tests continue to pass.
5. Preview-safe Playwright coverage drives the synthetic inbox workflow used by demo media and visual validation.

## Implementation Plan

1. Add incoming intake data models and migrations in `invoices`, keeping outgoing `Invoice` untouched.
2. Add IMAP source/routing services for message parsing, artifact extraction, body PDF rendering, text normalization, issuer scoring, duplicate fingerprinting, and sanitized provenance.
3. Add a manual polling/import command that supports an IMAP source and a synthetic fixture path for tests/evidence.
4. Add inbox list/detail/review/conversion views and forms under the expenses area, because paid conversion targets `Expense`.
5. Add per-source and per-issuer routing settings UI that stores credential references and routing rules without raw secrets.
6. Add conversion logic that copies the selected artifact to the created expense attachment, stores provenance, links the candidate/artifact/expense, and invalidates dashboard caches.
7. Add documentation, tests, synthetic fixtures, and preview-safe evidence scripts.

## Task List

- [ ] Add incoming invoice data model
  - [ ] Add `IncomingEmailSource`, `IssuerEmailRoutingRule`, `IncomingInvoiceCandidate`, and `IncomingInvoiceArtifact` models with status/provider/kind choices.
  - [ ] Limit the source provider for this issue to IMAP while keeping future provider expansion non-disruptive.
  - [ ] Add upload path helpers for incoming artifacts under `media/incoming-invoices/...`.
  - [ ] Add uniqueness/index constraints for source message ids, status/date filtering, issuer filtering, and artifact hashes.
  - [ ] Add safe admin registrations that do not expose secrets or full raw email bodies.
  - [ ] Add model tests for constraints, status transitions, access-relevant relationships, file paths, and display helpers.

- [ ] Build IMAP polling, artifact, routing, and duplicate services
  - [ ] Add IMAP message fetching for configured folder/search scope without mutating mailbox state.
  - [ ] Add email parsing that captures sanitized headers, recipients, delivered-to values, text/html bodies, message/thread ids, and allowed attachments.
  - [ ] Add email-body PDF rendering using existing WeasyPrint/django-weasyprint dependencies.
  - [ ] Add source polling/import idempotency by source id plus provider message id, with fixture-backed import support for tests.
  - [ ] Add issuer scoring from aliases, delivered-to addresses, company names, VAT/tax ids, keywords, and artifact/body text.
  - [ ] Add duplicate detection for message ids, artifact SHA-256, invoice metadata fingerprints, and incoming-created expense provenance.

- [ ] Add incoming inbox review and conversion UI
  - [ ] Add URL routes, views, and templates for incoming inbox list, candidate detail/review, source settings, routing settings, artifact download/preview, and conversion confirmation.
  - [ ] Add filters for status, company, source, confidence, date, and missing review.
  - [ ] Add forms/actions for company override, artifact selection, not-invoice, needs-fetch, duplicate/link-existing, and duplicate override.
  - [ ] Add conversion form validation requiring confirmed issuer, selected artifact, paid state, paid date for expenses, amount, and description/vendor confirmation.
  - [ ] Create paid `Expense` records from confirmed candidates, attach the selected artifact, write provenance to `raw_data`, link the candidate, and invalidate dashboard caches.
  - [ ] Add view/form tests for permissions, filters, review actions, conversion success/failure, and duplicate handling.

- [ ] Integrate navigation, styling, and docs
  - [ ] Add navigation entry points that fit existing sidebar and active-company patterns.
  - [ ] Reuse existing tables, filters, badges, forms, page patterns, and Tabler icon style.
  - [ ] Add focused CSS only where existing design components are insufficient.
  - [ ] Update `README.md` and/or `docs/` with IMAP setup, credential-reference, polling, fixture, review, conversion, privacy, and rollback guidance.
  - [ ] Add regression tests that existing invoice and expense import screens still render and behave as before.

- [ ] Add preview-safe synthetic evidence support
  - [ ] Add sanitized `.eml`/attachment fixtures for attached-PDF, body-PDF, ambiguous-company, portal-link, and duplicate scenarios.
  - [ ] Add E2E seed/setup support for incoming sources, routing rules, and synthetic candidates.
  - [ ] Add an issue-specific Playwright spec for inbox review and paid conversion.
  - [ ] Add `scripts/demo-evidence.sh` and `scripts/visual-validation.sh` scenarios declared below, with target-aware visual validation behavior.

## Deployment / Rollout

Run the normal Django deployment with migrations. No scheduled worker or mailbox cron should be enabled by this issue.

Before enabling a production IMAP source, an operator must configure runtime credential references and a narrow folder/search scope. The first production poll should be run manually with a small limit and verified in the inbox before repeated polling.

Generated files live in `media/`. Rollback leaves created incoming rows and media files unused by older code; if cleanup is needed, handle it as an operator data-maintenance task after rollback.

## File-Level Changes

### Add

- `invoices/migrations/00xx_incoming_invoice_inbox.py` — schema for incoming source, routing rule, candidate, and artifact models.
- `invoices/services/incoming_email.py` — IMAP polling/import and email parsing.
- `invoices/services/incoming_invoice_artifacts.py` — artifact storage, hashing, body-PDF generation, and safe text extraction hooks.
- `invoices/services/incoming_invoice_routing.py` — issuer scoring and reasons.
- `invoices/services/incoming_invoice_conversion.py` — review transitions, duplicate handling, and conversion to `Expense`.
- `invoices/management/commands/poll_incoming_invoices.py` — manual IMAP poll/import command with fixture support.
- `expenses/templates/expenses/incoming_*.html` — inbox, detail/review, settings, and conversion screens.
- `tests/fixtures/incoming_email/` — sanitized synthetic email and artifact fixtures.
- `invoices/tests/test_incoming_invoice_*.py` and `expenses/tests/test_incoming_invoice_views.py` — focused model/service/view coverage.
- `tests/e2e/incoming-invoice-inbox.spec.js` — preview-safe browser workflow coverage.
- `scripts/demo-evidence.sh` — repo-owned demo evidence entrypoint.
- `scripts/visual-validation.sh` — repo-owned visual validation entrypoint.
- `docs/incoming-invoice-inbox.md` — operator/user documentation if a dedicated doc is clearer than adding to an existing docs page.

### Modify

- `invoices/models.py` — add incoming invoice models and helpers.
- `invoices/admin.py` — register safe incoming model admin views.
- `expenses/forms.py` or a new `expenses/forms_incoming.py` — add source, routing, review, and conversion forms.
- `expenses/views.py` — add incoming inbox/review/conversion views.
- `expenses/urls.py` — add incoming inbox routes.
- `invoices/templates/invoices/navbar.html` — add incoming inbox navigation.
- `invoices/static/invoices/css/design/components.css` and/or app CSS — add minimal reusable styling for inbox/review states if needed.
- `invoices/management/commands/seed_e2e_smoke.py` — seed synthetic incoming invoice data for E2E when needed.
- `README.md` and relevant `docs/` files — document setup, security, polling, and review workflow.

### Keep

- Existing outgoing `Invoice` behavior and PDF generation semantics.
- Existing `Expense` paid-date requirement unless the unpaid-bill open question changes scope.
- Existing expense statement import flow and mapping behavior.
- Managed workflow files and environment sample files.
- Gmail/OAuth, scheduled polling, provider-side labels, vendor-portal automation, and OCR as follow-up scope.

## Demo Media

### Scenario: incoming-invoice-review-conversion

#### Repo Command

./scripts/demo-evidence.sh incoming-invoice-review-conversion

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow and seed a synthetic IMAP incoming invoice source with issuer routing rules.
2. Import synthetic emails covering an attached invoice file, an email-body-only invoice, and an uncertain company match.
3. Open the incoming inbox and show the staged candidates with their review statuses and company suggestions.
4. Open a candidate detail page, review available artifacts, confirm the suggested company, select an artifact, and open conversion.
5. Convert the paid candidate into an expense and leave the UI on a reviewer-visible expense state with the selected attachment/provenance visible.
6. Return to the incoming inbox or filtered review state showing the uncertain candidate still awaiting review.

#### Screenshot Checkpoints

- incoming-source-seeded: full-page screenshot of the reviewer-visible incoming source/routing state created from synthetic data
- incoming-inbox-mixed-candidates: full-page screenshot of the incoming inbox with multiple candidate statuses visible
- incoming-body-pdf-artifact: full-page screenshot of a candidate detail state showing a generated email-body PDF artifact
- incoming-conversion-form: full-page screenshot of the conversion confirmation form before creating the expense
- incoming-converted-expense: full-page screenshot of the resulting expense state with the selected attachment visible
- incoming-uncertain-needs-review: full-page screenshot of the inbox/review state showing an uncertain candidate not auto-converted

## Visual Validation

### Identifier

incoming-invoice-inbox

### Capture Command

./scripts/visual-validation.sh incoming-invoice-inbox

### Steps

1. Authenticate through the repo-owned smoke-user flow.
2. In baseline mode, capture the existing Expenses page/sidebar fallback state because incoming inbox routes do not exist on the frozen baseline.
3. In current mode, seed synthetic incoming invoice data, open the incoming inbox list, candidate detail/review screen, conversion form, and converted expense state.
4. In current mode, verify PR-only routes/selectors only after navigating to the new incoming invoice states.
5. Capture broad full-page screenshots for each reviewer-visible state.

### Full-Page Checkpoints

- incoming-inbox-list: baseline fallback Expenses page; current incoming inbox list with filters and staged candidates
- incoming-candidate-review: baseline fallback Expenses page; current candidate detail/review page with artifacts, company suggestion, reasons, and warnings
- incoming-conversion-form: baseline fallback Expenses page; current conversion confirmation form
- incoming-converted-expense: baseline fallback Expenses page; current expense state showing the converted incoming invoice attachment/provenance context

### Expected Comparisons

- The `incoming-inbox-list` baseline/current pair should show the new incoming inbox navigation and list/filter layout without unrelated changes to the existing Expenses page style.
- The `incoming-candidate-review` baseline/current pair should show the new review-first detail layout with artifact choices and company-routing feedback.
- The `incoming-conversion-form` baseline/current pair should show the new conversion confirmation flow using existing form visual patterns.
- The `incoming-converted-expense` baseline/current pair should show the resulting expense state integrated with existing expense UI patterns.

## Open Questions

- Should this issue include a first-class unpaid supplier bill model, or should unpaid reviewed candidates remain unconverted with an explicit UI limitation until a follow-up issue?
- Should converted incoming invoice currency remain stored in Expense.raw_data like the existing expense importer, or should this issue add a first-class currency field to Expense?
