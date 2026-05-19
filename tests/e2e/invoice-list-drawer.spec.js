const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');

test('invoice list filter opens and saves the invoice drawer', async ({ page }, testInfo) => {
  const updatedNotes = `Updated by Playwright invoice drawer smoke test (retry ${testInfo.retry}).`;

  await loginToDashboard(page);

  await page.goto('/invoices/?status=all&date_range=all');

  await expect(page.getByRole('heading', { name: 'Invoices' })).toBeVisible();
  await expect(page.locator('.data-table tbody tr')).toHaveCount(4);

  await page.getByRole('button', { name: 'Draft' }).click();

  await expect(page).toHaveURL(/\/invoices\/\?.*status=draft/);
  await expect(page.getByRole('button', { name: 'Draft' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.data-table tbody tr')).toHaveCount(1);
  await expect(page.locator('.data-table tbody')).toContainText('E2E Client Northwind');
  await expect(page.locator('.data-table tbody')).toContainText('Smoke Website Retainer');

  await page.locator('.data-table tbody tr').first().locator('a.link-primary').first().click();
  await expect(page.getByRole('heading', { name: /Invoice / })).toBeVisible();

  await page.locator('[data-tab-group] a[href="#edit"]').click();
  await expect(page).toHaveURL(/\/invoices\/\d+\/\?tab=edit$/);

  const notesField = page.getByLabel('Notes');
  await expect(notesField).not.toHaveValue('');
  await notesField.fill(updatedNotes);
  await page.getByRole('button', { name: 'Save invoice' }).click();

  await expect(page).toHaveURL(/\/invoices\/\d+\/\?tab=edit$/);
  await expect(page.locator('#edit')).toHaveClass(/is-active/);
  await expect(notesField).toHaveValue(updatedNotes);
});
