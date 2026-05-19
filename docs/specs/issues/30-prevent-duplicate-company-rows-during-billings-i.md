# Overview

Prevent `import_billings` from creating duplicate `Company` rows when Billings customer external IDs churn, and provide a safe one-time cleanup path for already-orphaned duplicates.

The recommended cut is:
- add deterministic company matching inside the Billings customer import path before creating a new `Company`
- prefer strong identity fields first, then a conservative fallback when strong identity is absent
- clean up only orphan duplicate companies, not companies still linked to a `Customer` or `Issuer`
- defer database-level uniqueness until data is cleaned and normal edit flows are proven compatible

# Problem

`invoices_company` contains real duplicate rows in production. The import path currently looks up `Customer` by Billings external ID and, when that lookup misses, creates a fresh `Company` instead of first checking whether the business already exists in local data.

That makes the import idempotent only while the upstream Billings client ID stays stable. If the Billings-side customer record is replaced or rekeyed, the importer can create a second `Company` row for the same business and leave the older row orphaned.

The current model also has no uniqueness protection on `Company`, so the database does not prevent these duplicates.

# Proposed Outcome

Update `invoices/management/commands/import_billings.py` so customer import resolves the target `Company` in this order before creating a new row:

1. existing `Customer` by `external_id`
2. existing `Company` by normalized tax identifier / CIF (`customer_information_file_number`) when present
3. existing `Company` by normalized company name + normalized contact email when both are present
4. otherwise create a new `Company`

Matching should be conservative:
- normalize whitespace and casing before comparison
- treat blank tax IDs and blank emails as unusable for dedupe
- do not merge by name alone

Also add a one-time cleanup management command that:
- identifies duplicate groups using the same matching rules
- only targets orphan companies with no linked `Customer` and no linked `Issuer`
- shows a dry-run summary first
- requires explicit confirmation before deleting rows

A database uniqueness constraint should not be part of this issue unless implementation proves it is safe with current production data and existing manual company editing flows.

# Constraints / Non-Goals

- Do not merge or delete companies that are still linked to any `Customer` or `Issuer`.
- Do not dedupe by company name alone.
- Do not rewrite unrelated import behavior for projects, invoices, or payments.
- Do not require admin-only manual cleanup as the primary path.
- Do not add a `Company` uniqueness constraint by default in this issue.
- Do not run destructive cleanup without an explicit operator confirmation path and backup prerequisite.

# Acceptance Criteria

## User Outcome

1. Re-importing Billings data for the same business does not create a second `Company` row when the business already exists locally under the dedupe rules.
2. A Billings client whose upstream external ID changes is linked back to the existing company record instead of creating a replacement duplicate.
3. Existing orphan duplicate companies can be reviewed in a dry run and then removed safely with an explicit cleanup command.

## Technical Behavior

1. `import_billings` checks for an existing `Company` before creating one when `Customer.external_id` lookup misses.
2. Company matching prefers normalized `customer_information_file_number` when present.
3. Fallback matching uses normalized `name + contact_email` only when both values are non-blank.
4. The importer does not merge unrelated companies that share only a name.
5. When a matching company is reused, the imported `Customer` points to that existing company record.
6. Cleanup logic only deletes orphan `Company` rows with no linked `Customer` and no linked `Issuer`.
7. Cleanup logic reports what it would remove before deletion and requires an explicit confirmation flag for destructive execution.

## Operations / Deployment

1. Cleanup can be executed as a one-time post-backup operation without manual SQL edits.
2. Normal application deployment remains safe even if the cleanup command has not yet been run.
3. No database uniqueness constraint is added unless data compatibility is verified during implementation.

## Validation

1. Automated tests cover repeated imports where the same Billings client is imported more than once without creating duplicate companies.
2. Automated tests cover external-ID churn where a new Billings client ID maps back to an existing company by tax ID.
3. Automated tests cover fallback reuse by normalized company name + contact email.
4. Automated tests cover the negative case where matching data is too weak and a new company is still created.
5. Automated tests cover cleanup dry-run output and confirmed deletion behavior for orphan duplicates.

# Implementation Plan

1. Extract small normalization helpers for company identity fields used by the Billings importer.
2. Refactor customer import so company resolution is separated from customer creation/update logic.
3. Add conservative company matching queries in the defined priority order before `Company(...)` creation.
4. Add a dedicated cleanup management command for orphan duplicate companies with dry-run and explicit apply/confirm behavior.
5. Add importer and command tests that cover repeated imports, upstream ID churn, fallback matching, and safe cleanup behavior.
6. Reassess a model/database uniqueness constraint only after the importer and cleanup workflow are in place; keep it out unless clearly safe.

# Task List

- [x] Harden Billings company resolution
  - [x] Add normalization helpers for tax ID, company name, and contact email used during import matching
  - [x] Extract importer logic that resolves an existing company before creating a new one
  - [x] Implement company lookup priority: customer external ID, tax ID, then name + contact email fallback
  - [x] Preserve current customer update behavior after the resolved company is selected

- [x] Add orphan duplicate cleanup command
  - [x] Add a management command that groups candidate duplicate companies by the same dedupe keys
  - [x] Limit deletion candidates to companies with no linked customer and no linked issuer
  - [x] Add dry-run reporting with per-group counts and deletion totals
  - [x] Require an explicit destructive confirmation path and backup acknowledgement before deletion

- [x] Add regression coverage
  - [x] Add import tests proving repeated imports reuse the same company row
  - [x] Add import tests proving external-ID churn reuses an existing company by tax ID
  - [x] Add import tests proving normalized name + email fallback reuses an existing company and name-only matching does not
  - [x] Add cleanup-command tests for dry run, confirmed deletion, and protection of non-orphan companies

- [x] Validate rollout safety
  - [x] Verify the cleanup command can be run independently after deployment
  - [x] Verify no migration is required for the importer and cleanup-command cut
  - [x] Recheck whether a uniqueness constraint should remain deferred after tests and sample data review

# Deployment / Rollout

Deploy the importer change first so new duplicates stop being created. Run the orphan cleanup command only after a full database backup has been completed.

Recommended rollout:
- deploy application code with the new importer behavior
- run cleanup in dry-run mode on production and review the candidate counts
- confirm backup completion
- run the cleanup command in confirmed mode
- spot-check Django admin for duplicate reduction and validate that existing customers and issuers still resolve correctly

This work should not require a schema migration in the recommended cut.

# File-Level Changes

- Modify `invoices/management/commands/import_billings.py` to add company-level dedupe resolution before creating new `Company` rows
- Add `invoices/management/commands/cleanup_orphan_duplicate_companies.py` for one-time orphan duplicate cleanup
- Add `invoices/tests/test_import_billings.py` or extend the existing invoices test package with focused Billings import coverage
- Add cleanup-command tests under `invoices/tests/` for dry-run and confirmed deletion behavior
- Keep `invoices/models.py` unchanged for the recommended cut unless implementation later proves a safe uniqueness constraint
- Keep `invoices/admin.py` unchanged; admin is a verification surface, not the source of the bug

# Open Questions

None.
