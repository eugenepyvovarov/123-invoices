## Overview

Build an IMAP-only incoming invoice inbox for supplier invoices and receipts. The inbox stages fetched email candidates for review, suggests the correct issuer/company, stores candidate artifacts, and creates accounting records only after a user confirms the company, selected artifact, and paid status.

This issue uses the smaller confirmed scope: unpaid reviewed candidates remain in the incoming inbox as reviewed/unpaid and are not accounting records until a future supplier-bill/AP model exists. Paid candidates convert to existing `Expense` records. Incoming source currency is preserved in `Expense.raw_data`; this issue does not add first-class expense multi-currency fields.

## Problem

Supplier invoice emails currently have no safe intake workflow. Existing `Invoice` records are outgoing customer invoices and must not be reused for supplier bills. Existing `Expense` records require `paid_date`, so blindly converting fetched emails risks wrong company routing, fake payment dates, duplicate expenses, and lost source provenance.

The app also already stores imported expense currency metadata in `raw_data` while reporting on `Expense.amount`. Adding first-class expense currency fields would affect forms, imports, dashboards, totals, and formatting beyond this inbox MVP.

## Proposed Outcome

- Add incoming email source, issuer routing rule, candidate, and artifact models.
- Support one manually polled IMAP mailbox source with configured folder/search scope.
- Store fetched messages idempotently as review candidates before creating any expense.
- Save allowed attachments and generate an email-body PDF artifact when the body is useful or no suitable attachment exists.
- Suggest issuer/company using recipient aliases, delivered-to values, legal names, VAT/tax identifiers, keywords, and available candidate/artifact text.
- Keep uncertain matches in review states; never auto-convert fetched email.
- Add inbox list/detail/review UI with filters, artifacts, detection reasons, duplicate warnings, company override, and review actions.
- Convert paid reviewed candidates into `Expense` records linked to the source candidate and selected artifact.
- Mark unpaid reviewed candidates as reviewed/unpaid with confirmed metadata and clear UI messaging that no accounting record exists yet.
- Preserve provenance, source currency, source amount, selected artifact id/hash, and candidate id in `Expense.raw_data`.
- Use synthetic email fixtures for tests, demo media, and visual validation.

## Constraints / Non-Goals

- Do not change outgoing `Invoice` semantics.
- Do not add Gmail OAuth/API support; this issue is IMAP only.
- Do not implement scheduled polling, provider-side labels, mailbox mutation, email deletion/archive, or vendor-portal browser automation.
- Do not scrape broad personal mailboxes; polling must use configured IMAP folder/search scope.
- Do not store real IMAP passwords, tokens, messages, cookies, customer data, or secrets in git, tests, logs, markdown, screenshots, or fixtures.
- Do not make OCR mandatory; use deterministic text extraction only when available.
- Do not add a first-class unpaid supplier bill/AP ledger in this issue.
- Do not add `Expense.currency`, `Expense.exchange_rate`, or `Expense.base_currency_amount` in this issue.
- Preserve existing expense import behavior and company scoping.

## Acceptance Criteria

### User Outcome

1. A permitted user can open an incoming invoice inbox and view staged candidates.
2. A user can configure or seed one IMAP source without committing secrets.
3. A manual poll/import action creates inbox candidates without creating expenses or bills.
4. Candidate detail shows sender, subject, received date, suggested company, status, artifacts, extraction hints, detection reasons, warnings, and review actions.
5. The user can confirm or override the company before conversion.
6. The user can choose an attached PDF, generated email-body PDF, or another stored artifact as the final expense attachment.
7. A paid reviewed candidate can be converted into an `Expense` for the confirmed issuer with the selected artifact attached.
8. An unpaid reviewed candidate can be marked reviewed/unpaid without creating an `Expense`, with clear UI messaging that supplier bill tracking is deferred.
9. Rejected, not-invoice, duplicate, needs-fetch, converted, and reviewed/unpaid candidates remain visible in history.
10. Unclear company matches remain in `needs_review` and are not auto-converted.

### Technical Behavior

1. Incoming models are issuer-aware and enforce existing user/issuer access boundaries.
2. `IncomingEmailSource` supports IMAP provider metadata, enabled state, folder/search scope, cursor state, owner/admin user, optional issuer, and credential references only.
3. `IssuerEmailRoutingRule` stores per-issuer aliases, delivered-to addresses, legal names, VAT/tax identifiers, keywords, and confidence threshold settings.
4. `IncomingInvoiceCandidate` is unique per source/provider message id and stores sanitized headers/body/provider metadata, detection metadata, duplicate metadata, status, suggested/resolved issuer, selected artifact, reviewed/unpaid metadata, and linked converted expense when applicable.
5. `IncomingInvoiceArtifact` stores files under `media/`, records content type, size, SHA-256 hash, extracted text when available, parsed metadata, and invoice-likeness confidence.
6. Polling is non-destructive, idempotent, scoped to configured IMAP folder/search settings, and safe to rerun.
7. Portal-link-only candidates with no usable file/body invoice are marked `needs_fetch`.
8. Routing suggests an issuer only when exactly one issuer meets confidence requirements; otherwise the candidate stays `needs_review`.
9. Duplicate detection covers source/message id, artifact SHA-256, invoice metadata fingerprints, and incoming-created expense provenance.
10. Conversion requires confirmed issuer, selected artifact, paid state, paid date for expenses, amount, and description/vendor confirmation.
11. Created expenses include incoming-invoice provenance and source currency/source amount in `raw_data`.
12. Dashboard/cache state is invalidated after creating expenses.

### Operations / Deployment

1. Database migrations create the new incoming source, routing, candidate, and artifact tables.
2. Runtime artifacts are stored under `media/` and are not committed.
3. Mailbox polling is manual only through a repo-owned management command.
4. Documentation covers IMAP setup, credential-reference expectations, fixture import, poll command usage, review workflow, unpaid limitation, currency handling, and security/privacy rules.
5. Rollback is a normal code rollback; already-created incoming rows/media may remain inert unless an operator performs separate cleanup.

### Validation

1. Django tests cover model constraints, upload paths, status transitions, idempotent polling/import, artifact hashing, email-body PDF generation, company routing, duplicate detection, review actions, paid conversion to `Expense`, reviewed/unpaid handling, issuer access scoping, and dashboard cache invalidation.
2. View/form tests cover inbox filters, candidate detail, company override, artifact selection, not-invoice, needs-fetch, duplicate/link-existing handling, paid conversion validation, and reviewed/unpaid UI.
3. Synthetic fixtures cover attached-PDF email, no-attachment body-PDF email, ambiguous-company email, portal-link-only email, duplicate message id, and duplicate file hash.
4. Existing outgoing invoice tests and existing expense import tests continue to pass.
5. Preview-safe Playwright coverage drives the synthetic inbox workflow used by demo media and visual validation.

## Implementation Plan

1. Add incoming intake models and migrations in `invoices`, keeping outgoing `Invoice` untouched.
2. Add IMAP polling/import services for scoped fetch, message parsing, artifact storage, body-PDF generation, issuer scoring, duplicate detection, and sanitized provenance.
3. Add a manual management command that can poll a configured IMAP source or import synthetic `.eml` fixtures.
4. Add inbox list/detail/review/conversion views and forms under the expenses area because paid conversion targets `Expense`.
5. Add source/routing settings UI using credential references rather than raw stored secrets.
6. Add paid conversion logic that copies the selected artifact to the `Expense` attachment, writes provenance/currency metadata to `raw_data`, links candidate/artifact/expense, and invalidates dashboard caches.
7. Add reviewed/unpaid handling that stores confirmed issuer, selected artifact, and metadata while leaving the candidate unconverted.
8. Add docs, focused tests, synthetic fixtures, and preview-safe evidence scripts.

## Task List

- [x] Add incoming invoice data model
  - [x] Add `IncomingEmailSource`, `IssuerEmailRoutingRule`, `IncomingInvoiceCandidate`, and `IncomingInvoiceArtifact` models with status/provider/kind choices.
  - [x] Limit the source provider for this issue to IMAP while keeping future provider expansion non-disruptive.
  - [x] Add reviewed/unpaid candidate state and fields for confirmed issuer, selected artifact, metadata, and conversion limitation messaging.
  - [x] Add incoming artifact upload paths under `media/incoming-invoices/...`.
  - [x] Add uniqueness/index constraints for source message ids, status/date filtering, issuer filtering, and artifact hashes.
  - [x] Add model/admin tests for constraints, status transitions, relationships, file paths, and display helpers.

- [ ] Build IMAP polling, artifact, routing, and duplicate services
  - [ ] Add IMAP message fetching for configured folder/search scope without mutating mailbox state.
  - [ ] Add email parsing for sanitized headers, recipients, delivered-to values, text/html bodies, message/thread ids, and allowed attachments.
  - [ ] Add email-body PDF rendering using existing WeasyPrint dependencies.
  - [ ] Add fixture-backed import support for tests and evidence.
  - [ ] Add issuer scoring from aliases, delivered-to addresses, company names, VAT/tax ids, keywords, and available artifact/body text.
  - [ ] Add duplicate detection for message ids, artifact hashes, invoice fingerprints, and incoming-created expense provenance.

- [ ] Add incoming inbox review and conversion UI
  - [ ] Add URL routes, views, templates, and forms for inbox list, candidate detail/review, source settings, routing settings, artifact download/preview, and conversion confirmation.
  - [ ] Add filters for status, company, source, confidence, date, and missing review.
  - [ ] Add actions for company override, artifact selection, not-invoice, needs-fetch, reviewed/unpaid, duplicate/link-existing, and duplicate override.
  - [ ] Add conversion validation requiring confirmed issuer, selected artifact, paid state, paid date for expenses, amount, and description/vendor confirmation.
  - [ ] Create paid `Expense` records from confirmed candidates, attach the selected artifact, write provenance/source currency metadata to `raw_data`, link records, and invalidate dashboard caches.
  - [ ] Add view/form tests for permissions, filters, review actions, conversion success/failure, reviewed/unpaid state, and duplicate handling.

- [ ] Integrate navigation, styling, docs, and evidence support
  - [ ] Add navigation entry points that fit the existing sidebar and active-company patterns.
  - [ ] Reuse existing tables, filters, badges, forms, feedback components, and Tabler icon style.
  - [ ] Add focused CSS only where existing design components are insufficient.
  - [ ] Update `README.md` and/or `docs/` with IMAP setup, credential references, polling, fixtures, review, paid conversion, unpaid limitation, currency metadata, privacy, and rollback guidance.
  - [ ] Add sanitized synthetic fixtures and E2E seed/setup support for incoming sources, routing rules, and candidates.
  - [ ] Add issue-specific Playwright coverage plus the demo and visual-validation script scenarios declared below.

## Deployment / Rollout

Run the normal Django deployment with migrations. Do not enable any scheduled worker or mailbox cron in this issue.

Before enabling a production IMAP source, an operator must configure runtime credential references and a narrow folder/search scope. The first production poll should be run manually with a small limit and verified in the inbox before repeated polling.

Generated files live in `media/`. Rollback leaves created incoming rows and media files unused by older code; if cleanup is needed, handle it as an operator data-maintenance task after rollback.

## File-Level Changes

### Add

- `invoices/migrations/00xx_incoming_invoice_inbox.py` — schema for incoming source, routing rule, candidate, and artifact models.
- `invoices/services/incoming_email.py` — IMAP polling/import and email parsing.
- `invoices/services/incoming_invoice_artifacts.py` — artifact storage, hashing, body-PDF generation, and safe text extraction hooks.
- `invoices/services/incoming_invoice_routing.py` — issuer scoring and reasons.
- `invoices/services/incoming_invoice_conversion.py` — review transitions, reviewed/unpaid handling, duplicate handling, and paid conversion to `Expense`.
- `invoices/management/commands/poll_incoming_invoices.py` — manual IMAP poll/import command with fixture support.
- `expenses/templates/expenses/incoming_*.html` — inbox, detail/review, settings, and conversion screens.
- `tests/fixtures/incoming_email/` and/or `tests/e2e/fixtures/incoming-email/` — sanitized synthetic email and artifact fixtures.
- `invoices/tests/test_incoming_invoice_*.py` and `expenses/tests/test_incoming_invoice_views.py` — focused model/service/view coverage.
- `tests/e2e/incoming-invoice-inbox.spec.js` — preview-safe browser workflow coverage.
- `scripts/demo-evidence.sh` — repo-owned demo evidence entrypoint.
- `scripts/visual-validation.sh` — repo-owned visual validation entrypoint.
- `docs/incoming-invoice-inbox.md` — dedicated user/operator documentation if clearer than updating an existing docs page.

### Modify

- `invoices/models.py` — add incoming invoice models and helpers.
- `invoices/admin.py` — register safe incoming model admin views.
- `expenses/forms.py` or new `expenses/forms_incoming.py` — add source, routing, review, reviewed/unpaid, and conversion forms.
- `expenses/views.py` — add incoming inbox/review/conversion views.
- `expenses/urls.py` — add incoming inbox routes.
- `invoices/templates/invoices/navbar.html` — add incoming inbox navigation.
- `invoices/static/invoices/css/design/components.css` and/or app CSS — add minimal reusable styling for inbox/review states if needed.
- `invoices/management/commands/seed_e2e_smoke.py` — seed synthetic incoming invoice data for E2E when needed.
- `README.md` and relevant `docs/` files — document setup, security, polling, review workflow, unpaid limitation, and currency handling.

### Keep

- Existing outgoing `Invoice` behavior and PDF generation semantics.
- Existing `Expense.paid_date` requirement.
- Existing `Expense` currency storage pattern, with incoming source currency preserved in `raw_data`.
- Existing expense statement import flow and mapping behavior.
- Managed workflow files and environment sample files.
- Gmail/OAuth, scheduled polling, provider-side labels, vendor-portal automation, OCR, first-class supplier bills, and first-class expense multi-currency as follow-up scope.

## Demo Media

### Scenario: incoming-invoice-review-conversion

#### Repo Command

./scripts/demo-evidence.sh incoming-invoice-review-conversion

#### Outputs

video + screenshots

#### Steps

1. Sign in through the repo-owned smoke-user flow and seed a synthetic IMAP incoming invoice source with issuer routing rules.
2. Import synthetic emails covering an attached invoice file, an email-body-only invoice, an uncertain company match, and an unpaid reviewed item.
3. Open the incoming inbox and show the staged candidates with their review statuses and company suggestions.
4. Open a candidate detail page, review available artifacts, confirm the suggested company, select an artifact, and open conversion.
5. Convert a paid candidate into an expense and leave the UI on a reviewer-visible expense state with the selected attachment/provenance visible.
6. Return to the incoming inbox or filtered review state showing the uncertain candidate still awaiting review and the unpaid reviewed item not converted.

#### Screenshot Checkpoints

- incoming-source-seeded: full-page screenshot of the reviewer-visible incoming source/routing state created from synthetic data
- incoming-inbox-mixed-candidates: full-page screenshot of the incoming inbox with multiple candidate statuses visible
- incoming-body-pdf-artifact: full-page screenshot of a candidate detail state showing a generated email-body PDF artifact
- incoming-reviewed-unpaid: full-page screenshot of a reviewed unpaid candidate with explicit not-converted limitation messaging
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
2. Run target-aware capture logic based on `OPENCODE_VISUAL_VALIDATION_TARGET=baseline|current`.
3. In baseline mode, capture the existing Expenses page/sidebar fallback state because incoming inbox routes do not exist on the frozen baseline.
4. In current mode, seed synthetic incoming invoice data, open the incoming inbox list, candidate detail/review screen, reviewed/unpaid state, conversion form, and converted expense state.
5. In current mode, verify PR-only routes/selectors only after navigating to the new incoming invoice states.
6. Capture broad full-page screenshots for each reviewer-visible state.

### Full-Page Checkpoints

- incoming-inbox-list: baseline fallback Expenses page; current incoming inbox list with filters and staged candidates
- incoming-candidate-review: baseline fallback Expenses page; current candidate detail/review page with artifacts, company suggestion, reasons, and warnings
- incoming-reviewed-unpaid: baseline fallback Expenses page; current reviewed unpaid state with clear limitation messaging
- incoming-conversion-form: baseline fallback Expenses page; current conversion confirmation form
- incoming-converted-expense: baseline fallback Expenses page; current expense state showing the converted incoming invoice attachment/provenance context

### Expected Comparisons

- The `incoming-inbox-list` baseline/current pair should show the new incoming inbox navigation and list/filter layout without unrelated changes to the existing Expenses page style.
- The `incoming-candidate-review` baseline/current pair should show the new review-first detail layout with artifact choices and company-routing feedback.
- The `incoming-reviewed-unpaid` baseline/current pair should show the explicit unpaid limitation state using existing feedback patterns.
- The `incoming-conversion-form` baseline/current pair should show the new conversion confirmation flow using existing form visual patterns.
- The `incoming-converted-expense` baseline/current pair should show the resulting expense state integrated with existing expense UI patterns.

## Open Questions

None.
