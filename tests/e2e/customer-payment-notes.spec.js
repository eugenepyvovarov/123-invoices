const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const CUSTOMER_NAME = 'E2E Client Northwind';
const PAYMENT_NOTES = 'Use the customer-specific IBAN for Northwind country payments.';
const IS_BASELINE_VISUAL = process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline';

test.use({ storageState: { cookies: [], origins: [] } });

async function openCustomerEditTab(page) {
  await page.setViewportSize({ width: 1600, height: 1200 });
  await loginToDashboard(page);

  await page.getByRole('link', { name: CUSTOMER_NAME }).first().click();
  await expect(page.getByRole('heading', { level: 1, name: CUSTOMER_NAME })).toBeVisible();

  await page.locator('[data-tab-group]').getByRole('link', { name: 'Edit' }).click();
  await expect(page).toHaveURL(/\?tab=edit$/);
  await expect(page.getByRole('heading', { name: 'Billing defaults' })).toBeVisible();
}

test('customer payment notes override demo', async ({ page }, testInfo) => {
  test.skip(
    process.env.OPENCODE_DEMO_SCENARIO !== 'customer-payment-notes-override',
    'This evidence test only runs for the customer payment notes override demo scenario.',
  );
  test.skip(
    process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline',
    'The override demo requires the current customer payment notes field.',
  );

  await openCustomerEditTab(page);

  const paymentNotes = page.getByLabel('Payment notes');
  await expect(paymentNotes).toBeVisible();
  await paymentNotes.fill(PAYMENT_NOTES);
  await page.getByRole('button', { name: 'Save customer' }).click();

  await expect(page).toHaveURL(/\?tab=edit$/);
  await expect(page.getByText('Customer saved successfully')).toBeVisible();
  await expect(page.getByLabel('Payment notes')).toHaveValue(PAYMENT_NOTES);
  await captureCheckpointScreenshot(page, testInfo, 'customer-payment-notes-edit', { fullPage: true });

  await page.locator('[data-tab-group]').getByRole('link', { name: 'Invoices' }).click();
  const invoiceLink = page.locator('#invoices tbody a.link-primary').filter({ hasText: /^#/ }).first();
  await expect(invoiceLink).toBeVisible();
  await invoiceLink.click();

  await expect(page.getByRole('heading', { level: 1, name: /Invoice/ })).toBeVisible();
  const previewFrame = page.frameLocator('#invoice-preview-frame');
  await expect(previewFrame.getByText('Payment Notes')).toBeVisible();
  await expect(previewFrame.getByText(PAYMENT_NOTES)).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'customer-payment-notes-pdf', { fullPage: true });
});

test('customer edit billing defaults visual capture', async ({ page }, testInfo) => {
  test.skip(
    process.env.OPENCODE_VISUAL_VALIDATION_IDENTIFIER !== 'customer-payment-notes-billing-defaults',
    'This evidence test only runs for the customer payment notes billing defaults visual identifier.',
  );

  await openCustomerEditTab(page);

  if (!IS_BASELINE_VISUAL) {
    await expect(page.getByLabel('Payment notes')).toBeVisible();
  }

  await captureCheckpointScreenshot(page, testInfo, 'customer-edit-billing-defaults', { fullPage: true });
});
