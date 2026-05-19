const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');

test('switching companies updates company-scoped dashboard content', async ({ page }) => {
  await loginToDashboard(page);
  const recentInvoices = page.getByTestId('dashboard-recent-invoices');

  await expect(page.getByTestId('company-switcher-active-name')).toHaveText('E2E Smoke Alpha LLC');
  await expect(page.getByTestId('company-switcher-option').filter({ hasText: 'E2E Smoke Alpha LLC' })).toHaveAttribute('aria-current', 'true');
  await expect(recentInvoices).toContainText('E2E Client Northwind');
  await expect(recentInvoices).toContainText('Smoke Website Retainer');
  await expect(recentInvoices).not.toContainText('E2E Client Southridge');
  await expect(recentInvoices).not.toContainText('Smoke Mobile App');

  await page.getByTestId('company-switcher-toggle').click();
  await page.getByTestId('company-switcher-option').filter({ hasText: 'E2E Smoke Beta LLC' }).click();

  await expect(page).toHaveURL(/\/(dashboard\/)?$/);
  await expect(page.getByTestId('company-switcher-active-name')).toHaveText('E2E Smoke Beta LLC');
  await expect(page.getByTestId('company-switcher-option').filter({ hasText: 'E2E Smoke Beta LLC' })).toHaveAttribute('aria-current', 'true');
  await expect(recentInvoices).toContainText('E2E Client Southridge');
  await expect(recentInvoices).toContainText('Smoke Mobile App');
  await expect(recentInvoices).not.toContainText('E2E Client Northwind');
  await expect(recentInvoices).not.toContainText('Smoke Website Retainer');
});
