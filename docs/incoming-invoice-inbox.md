# Incoming invoice inbox

The incoming invoice inbox stages supplier invoice emails for review before any
accounting record is created. This first version supports IMAP sources only.

## IMAP source setup

Create an incoming source from **Expenses → Incoming inbox → Source settings**.
Use a narrow folder and search query such as a dedicated invoice folder or label;
do not point the source at an unrestricted personal mailbox. The source stores a
credential reference string only, for example `env:INCOMING_IMAP_PASSWORD` or a
name from the deployment secret store. Raw IMAP passwords, OAuth tokens, cookies,
or real messages must not be committed to git, screenshots, markdown, fixtures,
logs, or issue comments.

Manual polling is the only supported runtime behavior in this issue:

```bash
python manage.py poll_incoming_invoices --source-id 1 --host imap.example.com --username invoices@example.com --limit 10
```

The password is read from `INCOMING_IMAP_PASSWORD` by default, or from another
environment variable named with `--password-env`. Polling uses IMAP
`BODY.PEEK[]`, selects the configured folder read-only, and does not delete,
archive, or mark messages handled.

## Synthetic fixture import

Tests, demos, and local review should use sanitized fixtures under
`tests/fixtures/incoming_email/`:

```bash
python manage.py poll_incoming_invoices --source-id 1 --fixture-dir tests/fixtures/incoming_email
```

The fixture set covers an attached PDF invoice, an email-body-only invoice that
generates an email-body PDF artifact, an ambiguous company match, a portal-link
message that needs manual fetch, a duplicate message id, and a duplicate file
hash.

## Review workflow

Fetched messages become incoming candidates in **Expenses → Incoming inbox**.
Users can filter by status, company, source, confidence, date, or missing review.
Candidate detail shows the sender, subject, received date, suggested/confirmed
company, artifacts, detection reasons, and duplicate warnings. Review actions let
the user confirm or override the company, choose the final artifact, mark the item
not an invoice, mark it as needing manual fetch, mark/link duplicates, or proceed
to conversion.

Company routing suggests a company from recipient aliases, Delivered-To values,
legal names, VAT/tax identifiers, keywords, and candidate/artifact text. Unclear
or conflicting matches remain in `needs_review`; polling never creates expenses.

## Paid conversion and unpaid limitation

Paid candidates can be converted into `Expense` records only after the user
confirms the company, selected artifact, vendor/description, amount, currency,
and paid date. The selected artifact is copied to the expense attachment and the
expense `raw_data` stores incoming provenance, source amount, source currency,
candidate id, selected artifact id, and file hash.

Unpaid candidates are marked reviewed/unpaid and remain in inbox history. They
are explicitly not accounting records because the current `Expense` model
requires `paid_date`; supplier bill/AP tracking is deferred to a future model.

## Privacy, media, and rollback

Generated attachments and email-body PDFs are stored under `media/` and are not
tracked by git. Diagnostics should stay sanitized and should not expose raw
credentials or customer messages. Rollback is a normal code rollback; existing
incoming rows and media files remain inert for older code unless an operator runs
a separate data cleanup.
