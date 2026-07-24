const { test, expect } = require('@playwright/test');
const path = require('path');
const { execFileSync } = require('child_process');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const E2E_EMAIL = process.env.E2E_SMOKE_EMAIL || 'e2e-smoke@example.com';
const IS_BASELINE_VISUAL = process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline';
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PYTHON_BIN = process.env.PLAYWRIGHT_PYTHON_BIN || process.env.PYTHON_BIN || 'python3';

function clearSmokeUserApiTokens() {
  if (process.env.OPENCODE_PREVIEW_PUBLIC_URL) {
    return;
  }

  execFileSync(
    PYTHON_BIN,
    [
      'manage.py',
      'shell',
      '-c',
      [
        'from django.contrib.auth import get_user_model',
        `User = get_user_model()`,
        `user = User.objects.get(email=${JSON.stringify(E2E_EMAIL)})`,
        'user.api_tokens.all().delete()',
      ].join('; '),
    ],
    {
      cwd: REPO_ROOT,
      env: process.env,
      stdio: 'pipe',
    },
  );
}

test.use({ storageState: { cookies: [], origins: [] }, video: 'on' });

async function openUserSettings(page, viewport = { width: 1600, height: 1200 }) {
  await page.setViewportSize(viewport);
  await loginToDashboard(page);
  await page.goto('/accounts/user-settings/');
  await expect(page.getByRole('heading', { level: 1, name: 'User settings' })).toBeVisible();
}

async function expectApiTokenSettingsVisible(page) {
  await expect(page.getByTestId('invoices-api-token-settings')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Invoices API tokens' })).toBeVisible();
  await expect(page.getByText('These are separate from the Expense import AI provider key below.')).toBeVisible();
  await expect(page.getByTestId('expense-ai-provider-settings')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Expense import AI provider' })).toBeVisible();
}

async function expectApiTokenSettingsStacked(page) {
  const createPanel = page.locator('.api-token-settings__create-column');
  const listPanel = page.locator('.api-token-settings__list-column');
  await expect(createPanel).toBeVisible();
  await expect(listPanel).toBeVisible();

  const createBox = await createPanel.boundingBox();
  const listBox = await listPanel.boundingBox();
  expect(createBox).not.toBeNull();
  expect(listBox).not.toBeNull();
  expect(listBox.y).toBeGreaterThan(createBox.y + createBox.height - 1);
}

test('api token settings management demo', async ({ page }, testInfo) => {
  test.skip(
    process.env.OPENCODE_DEMO_SCENARIO !== 'api-token-settings-management',
    'This evidence test only runs for the API token settings management demo scenario.',
  );

  clearSmokeUserApiTokens();
  await openUserSettings(page);
  await expectApiTokenSettingsVisible(page);
  await expect(page.getByTestId('api-token-empty-state')).toBeVisible();
  await expect(page.getByText('No Invoices API tokens yet')).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'api-token-empty-state', { fullPage: true });

  const tokenName = `E2E settings token ${Date.now()}`;
  await page.getByLabel('Token name').fill(tokenName);
  await page.getByRole('button', { name: 'Create API token' }).click();

  await expect(page.getByText('Invoices API token created. Copy it now; it will not be shown again.')).toBeVisible();
  await expect(page.getByTestId('api-token-plaintext-reveal')).toBeVisible();
  await expect(page.getByLabel('New Invoices API token')).toHaveValue(/^inv_[0-9a-f]{8}_.+/);

  const tokenRow = page.getByTestId('api-token-list').locator('tbody tr').filter({ hasText: tokenName });
  await expect(tokenRow).toBeVisible();
  await expect(tokenRow.getByText('Active')).toBeVisible();
  await expect(tokenRow.getByText('No expiry')).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'api-token-created', { fullPage: true });

  await tokenRow.getByRole('button', { name: 'Revoke' }).click();
  await expect(page.getByText('Invoices API token revoked.')).toBeVisible();

  const revokedRow = page.getByTestId('api-token-list').locator('tbody tr').filter({ hasText: tokenName });
  await expect(revokedRow).toBeVisible();
  await expect(revokedRow.getByText('Revoked').first()).toBeVisible();
  await expect(page.getByTestId('api-token-plaintext-reveal')).toHaveCount(0);
  await expectApiTokenSettingsVisible(page);
  await captureCheckpointScreenshot(page, testInfo, 'api-token-revoked', { fullPage: true });
});

test('api token settings visual capture', async ({ page }, testInfo) => {
  test.skip(
    process.env.OPENCODE_VISUAL_VALIDATION_IDENTIFIER !== 'api-token-settings',
    'This evidence test only runs for the API token settings visual identifier.',
  );

  await openUserSettings(page);

  if (!IS_BASELINE_VISUAL) {
    await expectApiTokenSettingsVisible(page);
  }

  await captureCheckpointScreenshot(page, testInfo, 'user-settings-api-tokens-desktop', { fullPage: true });

  await page.setViewportSize({ width: 760, height: 1200 });
  await page.goto('/accounts/user-settings/');
  await expect(page.getByRole('heading', { level: 1, name: 'User settings' })).toBeVisible();

  if (!IS_BASELINE_VISUAL) {
    await expectApiTokenSettingsVisible(page);
    await expectApiTokenSettingsStacked(page);
  }

  await captureCheckpointScreenshot(page, testInfo, 'user-settings-api-tokens-narrow', { fullPage: true });
});
