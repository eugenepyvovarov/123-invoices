# Documentation

This folder contains current project documentation. Historical task specs live
under `docs/specs/issues/`; use them as task history, not as the primary source
for current setup or operations.

## Current Docs

- [Development](development.md): repository layout, local environment, common
  commands, validation, and generated-file rules.
- [API](api.md): authenticated REST API token setup, endpoint examples,
  filters, reports, PDFs, errors, and expense uploads.
- [Deployment](deployment.md): Docker image build, Compose runtime, live
  rollout, and verification checks.
- [MCP server](mcp-server.md): OAuth-protected Streamable HTTP endpoint,
  CIMD/pre-registration, scopes, environment values, upstream API credential
  setup, artifact limits, client examples, and operational checks.
- [Backups](backups.md): manual and scheduled backup behavior, timezone rules,
  locking, object key layout, and operator checks.
- [Incoming invoice inbox](incoming-invoice-inbox.md): IMAP source setup,
  fixture import, review-first conversion, unpaid limitations, privacy, and
  rollback guidance.
- [Automation](automation.md): OpenCode/Gitea automation contract, managed files,
  preview/evidence behavior, and production artifact publication.
- [Design contract](../DESIGN.md): UI tokens, layout conventions, component
  rules, and visual-validation guidance.
- [Agent notes](../AGENTS.md): concise repository instructions for coding
  agents working in this checkout.

## Maintenance Rules

- Update the README when the first-run path, supported runtime, or validation
  commands change.
- Update the relevant doc in this folder when deployment, backup, automation, or
  development behavior changes.
- Update `DESIGN.md` when a UI change intentionally changes shared visual
  patterns, component conventions, or screenshot guidance.
- Do not add old task plans or one-off notes to the repository root. Keep task
  history in issues or `docs/specs/issues/`.
