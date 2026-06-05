const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const DEFAULT_PERIOD_CHECKPOINT = process.env.OPENCODE_DEMO_SCENARIO === 'rolling-year-period-default'
  ? 'dashboard-rolling-year-default'
  : 'dashboard-period-default';

test('dashboard default period evidence', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1200 });
  await loginToDashboard(page);
  await page.goto('/dashboard/');

  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  const periodSelect = page.locator('#dashboard-period');
  await expect(periodSelect).toBeVisible();

  if (process.env.OPENCODE_VISUAL_VALIDATION_TARGET !== 'baseline') {
    await expect(periodSelect).toHaveValue('rolling_year');
    await expect(periodSelect.locator('option:checked')).toHaveText('Rolling Year');
    await expect(page.getByText('Invoiced Rolling Year')).toBeVisible();
  }

  await captureCheckpointScreenshot(page, testInfo, DEFAULT_PERIOD_CHECKPOINT, { fullPage: true });
});
