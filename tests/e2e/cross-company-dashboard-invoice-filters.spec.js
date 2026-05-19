const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

async function openCrossCompanyDashboard(page) {
  await loginToDashboard(page);

  await page.getByTestId('company-switcher-toggle').click();
  await page.getByTestId('company-switcher-menu').getByRole('link', { name: 'Dashboard', exact: true }).click();

  await expect(page).toHaveURL(/\/dashboard\/cross-company\/$/);
  await expect(page.getByTestId('company-switcher-active-name')).toHaveText('Dashboard');
  await expect(page.getByText('Combined activity across your available companies.')).toBeVisible();
}

async function selectMaxResults(page, selectTestId, value) {
  await Promise.all([
    page.waitForURL(new RegExp(`max_results=${value}`)),
    page.getByTestId(selectTestId).selectOption(value),
  ]);
}

test('cross-company dashboard invoice filters persist and share max results', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1200 });
  await openCrossCompanyDashboard(page);

  if (process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline') {
    await captureCheckpointScreenshot(page, testInfo, 'dashboard-invoice-filters-full-page', { fullPage: true });
    return;
  }

  const recentInvoices = page.getByTestId('dashboard-recent-invoices');
  const statusFilter = page.getByTestId('dashboard-invoice-status-filter');
  const invoiceMaxResults = page.getByTestId('dashboard-invoices-max-results');
  const paymentMaxResults = page.getByTestId('dashboard-payments-max-results');

  await expect(statusFilter).toBeVisible();
  await expect(invoiceMaxResults).toHaveValue('25');
  await expect(paymentMaxResults).toHaveValue('25');

  await captureCheckpointScreenshot(page, testInfo, 'dashboard-invoice-filters-full-page', { fullPage: true });

  await Promise.all([
    page.waitForURL(/invoice_status=/),
    statusFilter.getByRole('button', { name: 'Invoiced & Overdue' }).click(),
  ]);

  await expect(statusFilter.getByRole('button', { name: 'Invoiced & Overdue' })).toHaveAttribute('aria-pressed', 'true');
  await expect(recentInvoices.locator('tbody tr')).not.toHaveCount(0);
  await expect(recentInvoices).not.toContainText('Draft');
  await expect(recentInvoices).not.toContainText('Paid');

  await captureCheckpointScreenshot(page, testInfo, 'dashboard-invoice-status-filter-active', { fullPage: true });

  await selectMaxResults(page, 'dashboard-invoices-max-results', '50');
  await expect(invoiceMaxResults).toHaveValue('50');
  await expect(paymentMaxResults).toHaveValue('50');

  await selectMaxResults(page, 'dashboard-payments-max-results', '100');
  await expect(invoiceMaxResults).toHaveValue('100');
  await expect(paymentMaxResults).toHaveValue('100');
  await expect(statusFilter.getByRole('button', { name: 'Invoiced & Overdue' })).toHaveAttribute('aria-pressed', 'true');

  await page.reload();

  await expect(page).toHaveURL(/\/dashboard\/cross-company\//);
  await expect(invoiceMaxResults).toHaveValue('100');
  await expect(paymentMaxResults).toHaveValue('100');
  await expect(statusFilter.getByRole('button', { name: 'Invoiced & Overdue' })).toHaveAttribute('aria-pressed', 'true');
  await expect(recentInvoices).not.toContainText('Draft');
  await expect(recentInvoices).not.toContainText('Paid');

  await captureCheckpointScreenshot(page, testInfo, 'dashboard-shared-max-results-persisted', { fullPage: true });
});
