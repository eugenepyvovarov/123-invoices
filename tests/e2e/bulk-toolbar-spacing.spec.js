const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const IS_BASELINE_VISUAL = process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline';

test.use({ storageState: { cookies: [], origins: [] } });

async function openListPage(page, path, headingName) {
  await page.setViewportSize({ width: 1600, height: 1200 });
  await loginToDashboard(page);
  await page.goto(path);

  await expect(page.getByRole('heading', { level: 1, name: headingName })).toBeVisible();
  await expect(page.locator('.bulk-toolbar').first()).toBeVisible();
  await expect(page.locator('.data-table').first()).toBeVisible();

  if (!IS_BASELINE_VISUAL) {
    await expect(page.locator('.bulk-toolbar-stack').first()).toBeVisible();
  }
}

test('invoices bulk toolbar spacing visual capture', async ({ page }, testInfo) => {
  await openListPage(page, '/invoices/', 'Invoices');

  await captureCheckpointScreenshot(page, testInfo, 'invoices-bulk-toolbar-spacing', { fullPage: true });
});

test('expenses bulk toolbar spacing visual capture', async ({ page }, testInfo) => {
  await openListPage(page, '/expenses/', 'Expenses');

  await captureCheckpointScreenshot(page, testInfo, 'expenses-bulk-toolbar-spacing', { fullPage: true });
});
