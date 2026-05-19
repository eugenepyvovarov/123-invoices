const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

async function openFirstInvoicePdf(page) {
  const invoiceHref = await page.locator('.data-table tbody tr').first().locator('a.link-primary').first().getAttribute('href');
  expect(invoiceHref).toBeTruthy();
  const invoiceUrl = new URL(invoiceHref, page.url());
  const invoicePdfPath = `${invoiceUrl.pathname.replace(/\/$/, '')}/pdf/`;
  await page.goto(invoicePdfPath);
  await expect(page).toHaveURL(/\/invoices\/\d+\/pdf\/$/);
}

test('company bank accounts drive invoice selection and preview evidence', async ({ page }, testInfo) => {
  await loginToDashboard(page);

  await page.goto('/company/');
  await expect(page.getByRole('heading', { name: 'Company information' })).toBeVisible();
  const bankAccountsHeading = page.getByRole('heading', { name: 'Bank accounts' });

  if ((await bankAccountsHeading.count()) === 0) {
    await captureCheckpointScreenshot(page, testInfo, 'company-bank-accounts-settings-full-page', { fullPage: true });

    await page.goto('/projects/');
    await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
    await page.getByRole('link', { name: 'Smoke Website Retainer' }).click();
    await expect(page.getByRole('heading', { name: /Smoke Website Retainer/ })).toBeVisible();
    await page.getByRole('link', { name: 'New invoice' }).click();
    await expect(page.getByRole('heading', { name: 'Invoice details' })).toBeVisible();
    await captureCheckpointScreenshot(page, testInfo, 'invoice-bank-account-selector-full-page', { fullPage: true });

    await page.goto('/invoices/?status=all&date_range=all');
    await expect(page.getByRole('heading', { name: 'Invoices' })).toBeVisible();
    await openFirstInvoicePdf(page);
    await captureCheckpointScreenshot(page, testInfo, 'invoice-selected-bank-account-preview-full-page', { fullPage: true });
    return;
  }

  await expect(bankAccountsHeading).toBeVisible();
  await expect(page.locator('input[value="Alpha Primary EUR"]')).toBeVisible();
  await expect(page.locator('input[value="Alpha Project Reserve EUR"]')).toBeVisible();
  await expect(page.locator('#id_bank_accounts-0-is_default')).toBeChecked();

  if (process.env.OPENCODE_DEMO_SCENARIO === 'company-bank-accounts-invoice-selection') {
    await page.locator('#id_bank_accounts-1-account_details').fill(
      'IBAN ES98 7654 3210 9876 5432\nSWIFT RESERVEESB\nReference: Playwright safe reserve account',
    );
    await page.getByRole('button', { name: 'Save changes' }).click();
    await expect(page.getByRole('heading', { name: 'Company information' })).toBeVisible();
    await expect(page.locator('#id_bank_accounts-0-is_default')).toBeChecked();
    await expect(page.locator('input[value="Alpha Project Reserve EUR"]')).toBeVisible();
  }
  await captureCheckpointScreenshot(page, testInfo, 'company-bank-accounts-settings-full-page', { fullPage: true });

  await page.goto('/projects/');
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
  await page.getByRole('link', { name: 'Smoke Website Retainer' }).click();
  await expect(page.getByRole('heading', { name: /Smoke Website Retainer/ })).toBeVisible();
  await page.getByRole('link', { name: 'New invoice' }).click();

  await expect(page.getByRole('heading', { name: 'Invoice details' })).toBeVisible();
  const bankAccountSelect = page.getByLabel('Bank account');
  await expect(bankAccountSelect).toBeVisible();
  await expect(bankAccountSelect).toContainText('Alpha Primary EUR (default)');
  await expect(bankAccountSelect).toContainText('Alpha Project Reserve EUR');
  await bankAccountSelect.selectOption({ label: 'Alpha Project Reserve EUR' });
  await captureCheckpointScreenshot(page, testInfo, 'invoice-bank-account-selector-full-page', { fullPage: true });

  await page.goto('/invoices/?status=all&date_range=all');
  await expect(page.getByRole('heading', { name: 'Invoices' })).toBeVisible();
  await openFirstInvoicePdf(page);
  await expect(page.locator('body')).toContainText('ES98 7654 3210 9876 5432');
  await expect(page.locator('body')).not.toContainText('ES12 3456 7890 1234 5678');
  await captureCheckpointScreenshot(page, testInfo, 'invoice-selected-bank-account-preview-full-page', { fullPage: true });
});
