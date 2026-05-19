# Overview

Make Django messages render from the shared authenticated layout so success, error, info, and warning feedback appears consistently across all normal in-app pages that use `invoices/base.html`.

# Problem

Django messages are currently rendered only on some templates, which makes post-action feedback inconsistent. Views across `invoices`, `expenses`, and `accounts` already enqueue messages, but many base-layout pages do not display them after redirects. A few templates also render messages locally, creating duplicated presentation logic and inconsistent placement.

# Proposed Outcome

Add one shared message-rendering include to the normal app shell and place it in `invoices/base.html` so every page extending that layout shows queued Django messages in a consistent location and style.

Use the existing Django messages framework only. Keep the current visual pattern lightweight, but normalize message-level styling for the built-in message tags used in the codebase (`success`, `error`, `warning`, `info`). Remove page-level duplication on templates that currently render the same messages themselves.

# Constraints / Non-Goals

- Keep scope to the existing Django messages framework.
- Limit coverage to normal UI pages that extend the shared base layout.
- Do not redesign notifications into a toast system, modal, or live-updating component.
- Do not change message copy except where template rendering requires tag normalization.
- Do not expand this work to auth-only standalone templates such as login or OTP verification unless they are later moved onto the shared layout.

# Acceptance Criteria

## User Outcome

1. Any Django message queued before redirecting to a normal in-app page is visible when that page loads.
2. Messages appear in a consistent placement across pages that extend `invoices/base.html`.
3. Success, error, info, and warning messages remain readable and visually distinguishable without changing the underlying message text.

## Technical Behavior

1. Message rendering is implemented once from the shared base layout rather than repeated in individual base-extending templates.
2. Existing templates that extend `invoices/base.html` do not render duplicate message blocks after the shared layout change.
3. The shared renderer handles the message tags already emitted by the application and maps them to supported alert styles consistently.
4. Pages outside the V1 scope that use standalone layouts continue to behave as they do today.

## Operations / Deployment

1. The change requires no database migration, background job change, or environment configuration update.
2. Static assets needed for any new shared message styling are included in the normal collectstatic flow.

## Validation

1. Automated tests cover at least one success flow and one error or warning flow that redirect back to pages using the shared base layout.
2. Automated tests confirm that message text is present on representative pages from the main UI after redirects.
3. Automated tests confirm that templates which previously rendered messages inline do not show duplicated output once the shared renderer is in place.

# Implementation Plan

1. Audit current message usage in views and current template rendering so the shared solution covers actual message tags and the templates that already special-case messages.
2. Create a shared partial for Django messages and include it near the top of the content shell in `invoices/base.html`.
3. Normalize alert class handling for built-in message levels used by the app so `success`, `error`, `warning`, and `info` render consistently.
4. Remove redundant message loops from base-extending templates that currently render the same messages inline.
5. Add regression tests around representative redirect-driven message flows in the authenticated UI.

# Task List

- [x] Add shared message rendering to the base layout
  - [x] Create a reusable template partial for iterating over Django messages and mapping message tags to alert classes.
  - [x] Include the shared partial in `invoices/base.html` at a stable position above page-specific content.
  - [x] Add or adjust shared alert styles so all in-scope message levels render consistently.

- [x] Remove duplicate per-page message rendering
  - [x] Remove the inline Django message block from `accounts/templates/accounts/user_settings.html`.
  - [x] Remove the inline Django message block from `invoices/templates/invoices/backup_settings.html`.
  - [x] Verify other templates extending `invoices/base.html` do not need local message loops after the base change.

- [x] Add regression coverage for redirect-based feedback
  - [x] Add a test in the accounts settings suite proving a redirected success or error message renders through the shared base layout.
  - [x] Add a test in an invoices or backups suite proving a redirected warning, error, or success message renders through the shared base layout.
  - [x] Add assertions that the response contains one shared message rendering path rather than duplicated message output.

# Deployment / Rollout

This is a low-risk UI consistency change with no schema or data impact. Deploy normally with the next application release and include standard static asset collection. After deployment, manually verify a small set of common redirect flows in production-like environments, such as saving user settings, saving backup settings, and one representative invoices or expenses action that emits a message.

# File-Level Changes

## Add

- `invoices/templates/invoices/partials/messages.html` — shared renderer for Django messages in the normal app shell.

## Modify

- `invoices/templates/invoices/base.html` — include the shared message partial in the base layout.
- `invoices/templates/invoices/backup_settings.html` — remove duplicated inline message rendering.
- `accounts/templates/accounts/user_settings.html` — remove duplicated inline message rendering.
- `invoices/static/invoices/css/design/components.css` — add or normalize alert variants used by Django message levels.
- `accounts/tests/test_user_settings.py` — add redirect/message visibility regression coverage.
- `invoices/tests/test_backups.py` and/or another relevant authenticated UI test module — add shared-layout message visibility coverage.

## Keep

- `accounts/templates/accounts/login.html` — standalone auth template remains out of V1 scope.
- `accounts/templates/accounts/otp_verify.html` — standalone auth template remains out of V1 scope.
- View logic in `invoices/views.py`, `expenses/views.py`, and `accounts/views.py` that already uses Django messages, unless minor tag normalization is needed.

# Open Questions

None.
