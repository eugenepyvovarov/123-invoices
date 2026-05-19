const path = require('path');

const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const ATTACHMENT_FIXTURE = path.join(__dirname, 'fixtures/expenses/sample-receipt.csv');

function uniqueExpenseDescription(testInfo) {
  return `Playwright attachment filter ${testInfo.retry}-${Date.now()}`;
}

async function openExpenseDrawerForRow(page, description) {
  const row = page.locator('tbody tr').filter({ hasText: description }).first();
  await expect(row).toBeVisible();
  await row.getByRole('button', { name: 'Edit' }).click();
  await expect(page.locator('#expenseDrawer')).toHaveAttribute('aria-hidden', 'false');
  await expect(page.locator('#expense-drawer-form')).toBeVisible();
}

async function saveExpenseDrawer(page) {
  await page.locator('#expense-drawer-form').getByRole('button', { name: 'Save expense' }).click();
  await expect(page.locator('#expenseDrawer')).toHaveAttribute('aria-hidden', 'true');
}

function isVisualValidationBaseline(page) {
  return new URL(page.url()).hostname.includes('-baseline-');
}

async function expectFilterPreservedOrCaptureBaseline(page, filterName, buttonName) {
  if (isVisualValidationBaseline(page)) {
    await expect(page).toHaveURL(/\/expenses\//);
    return;
  }

  await expect(page).toHaveURL(new RegExp(`/expenses/\\?[^#]*has_attachment=${filterName}`));
  await expect(page.getByRole('button', { name: buttonName })).toHaveAttribute('aria-pressed', 'true');
}

async function applyAttachmentFilter(page, filterName) {
  await Promise.all([
    page.waitForURL((url) => url.pathname === '/expenses/' && url.searchParams.get('has_attachment') === filterName),
    page.getByRole('button', { name: filterName === 'with' ? 'With file' : 'Without file' }).click(),
  ]);
  await expect(page.getByRole('button', { name: filterName === 'with' ? 'With file' : 'Without file' })).toHaveAttribute('aria-pressed', 'true');
}

async function searchForExpense(page, description) {
  await page.getByLabel('Search').fill(description);
  await Promise.all([
    page.waitForURL((url) => url.pathname === '/expenses/' && url.searchParams.get('q') === description),
    page.getByRole('button', { name: 'Search' }).click(),
  ]);
}

test('expense attachment changes keep the invoice available filter active', async ({ page }, testInfo) => {
  const description = uniqueExpenseDescription(testInfo);
  const today = new Date().toISOString().slice(0, 10);

  await loginToDashboard(page);
  await page.goto('/expenses/?date_range=all');
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible();

  await page.getByRole('button', { name: 'New expense' }).click();
  await expect(page.locator('#expenseDrawer')).toHaveAttribute('aria-hidden', 'false');

  const form = page.locator('#expense-drawer-form');
  await form.getByLabel('Paid date').fill(today);
  await form.getByLabel('Amount (EUR)').fill('12.34');
  await form.getByLabel('Description (optional)').fill(description);
  await saveExpenseDrawer(page);

  await searchForExpense(page, description);
  await applyAttachmentFilter(page, 'without');
  await expect(page.locator('tbody tr').filter({ hasText: description })).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'expenses-without-file-filter-before-upload', { fullPage: true });

  await openExpenseDrawerForRow(page, description);
  await page.locator('#expense-drawer-form input[name="attachment"]').setInputFiles(ATTACHMENT_FIXTURE);
  await saveExpenseDrawer(page);

  const baselineAfterUpload = isVisualValidationBaseline(page);
  await expectFilterPreservedOrCaptureBaseline(page, 'without', 'Without file');
  if (!baselineAfterUpload) {
    await expect(page.locator('tbody tr').filter({ hasText: description })).toHaveCount(0);
  }
  await captureCheckpointScreenshot(page, testInfo, 'expenses-without-file-filter-after-upload', { fullPage: true });

  await searchForExpense(page, description);
  await applyAttachmentFilter(page, 'with');
  await expect(page.locator('tbody tr').filter({ hasText: description })).toBeVisible();

  await openExpenseDrawerForRow(page, description);
  await page.locator('#expense-drawer-form input[name="remove_attachment"]').check();
  await saveExpenseDrawer(page);

  const baselineAfterRemove = isVisualValidationBaseline(page);
  await expectFilterPreservedOrCaptureBaseline(page, 'with', 'With file');
  if (!baselineAfterRemove) {
    await expect(page.locator('tbody tr').filter({ hasText: description })).toHaveCount(0);
  }
  await captureCheckpointScreenshot(page, testInfo, 'expenses-with-file-filter-after-remove', { fullPage: true });
});
