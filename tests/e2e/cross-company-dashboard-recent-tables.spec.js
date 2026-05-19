const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

async function getHeaderTexts(table) {
  return table.locator('thead th').allTextContents();
}

test('cross-company dashboard hides project columns in recent tables', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1200 });
  await loginToDashboard(page);

  await page.getByTestId('company-switcher-toggle').click();
  await page.getByTestId('company-switcher-menu').getByRole('link', { name: 'Dashboard', exact: true }).click();

  const crossCompanyPage = page.locator('.page.dashboard-page');
  const recentInvoices = page.getByTestId('dashboard-recent-invoices');
  const recentPayments = page.getByTestId('dashboard-recent-payments');

  await expect(page).toHaveURL(/\/dashboard\/cross-company\/$/);
  await expect(page.getByTestId('company-switcher-active-name')).toHaveText('Dashboard');
  await expect(page.getByText('Combined activity across your available companies.')).toBeVisible();

  await captureCheckpointScreenshot(crossCompanyPage, testInfo, 'cross-company-dashboard-selected');

  expect.soft(await getHeaderTexts(recentInvoices)).toEqual(['#', 'Company', 'Date', 'Status', 'Client', 'Total']);
  await expect(recentInvoices).not.toContainText('Project');
  await expect(recentInvoices).toContainText('E2E Smoke Alpha LLC');
  await expect(recentInvoices).toContainText('E2E Smoke Beta LLC');
  await expect(recentInvoices).toContainText('E2E Client Northwind');
  await expect(recentInvoices).toContainText('E2E Client Southridge');
  await expect(recentInvoices).not.toContainText('Smoke Website Retainer');
  await expect(recentInvoices).not.toContainText('Smoke Mobile App');

  await captureCheckpointScreenshot(recentInvoices, testInfo, 'recent-invoices-without-project-column');

  expect.soft(await getHeaderTexts(recentPayments)).toEqual(['Date', 'Company', 'Invoice', 'Client', 'Amount']);
  await expect(recentPayments).not.toContainText('Project');
  await expect(recentPayments).toContainText('E2E Smoke Alpha LLC');
  await expect(recentPayments).toContainText('E2E Client Northwind');
  await expect(recentPayments.locator('tbody a')).toHaveCount(2);
  await expect(recentPayments).not.toContainText('Smoke Website Retainer');

  await captureCheckpointScreenshot(recentPayments, testInfo, 'recent-payments-without-project-column');
});
