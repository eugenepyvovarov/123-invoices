const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const PAYMENT_MEMO_PREFIX = 'Playwright invoice removal evidence payment';
const PAYMENT_AMOUNT = '25.00';
const isVisualValidationRun = Boolean(process.env.OPENCODE_VISUAL_VALIDATION_FULL_PAGE_CHECKPOINTS);

async function openSeededInvoice(page) {
  await page.goto('/projects/');
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
  await page.getByRole('link', { name: 'Smoke Website Retainer' }).click();

  await expect(page.getByRole('heading', { name: /Smoke Website Retainer/ })).toBeVisible();
  await page.locator('[data-tab-group]').getByRole('link', { name: 'Invoices' }).click();

  const paidInvoiceRow = page
    .locator('tbody tr')
    .filter({ has: page.getByRole('link', { name: /#/ }) })
    .filter({ hasText: '180.00 €' })
    .first();

  await expect(paidInvoiceRow).toBeVisible();
  await paidInvoiceRow.getByRole('link').first().click();
  await expect(page.getByRole('heading', { level: 1, name: /Invoice/ })).toBeVisible();
}

async function ensureAppliedPayment(page, testInfo) {
  const removeAction = page.getByRole('button', { name: 'Remove from invoice' }).first();
  if (await removeAction.isVisible().catch(() => false)) {
    return;
  }

  const memo = `${PAYMENT_MEMO_PREFIX} retry ${testInfo.retry}`;

  await expect(page.getByRole('button', { name: 'Add payment' }).first()).toBeVisible();
  await page.getByRole('button', { name: 'Add payment' }).first().click();
  await expect(page.getByTestId('payment-drawer')).toHaveAttribute('data-drawer-state', 'open');
  await expect(page.getByTestId('payment-form')).toHaveAttribute('data-submit-state', 'idle');

  await page.getByTestId('payment-amount-input').fill(PAYMENT_AMOUNT);
  await page.getByTestId('payment-memo-input').fill(memo);

  const invoiceId = page.url().match(/\/invoices\/(\d+)/)?.[1];
  expect(invoiceId).toBeTruthy();
  await expect(page.locator(`input[data-testid="payment-apply-invoice"][value="${invoiceId}"]`)).toBeChecked();
  await page.getByTestId('payment-submit').click();

  await page.waitForURL(/\/invoices\/\d+\/?(?:\?tab=preview)?$/);
  await expect(page.locator('tbody tr').filter({ hasText: memo })).toContainText('25.00 €');
}

test('invoice payment application removal is confirmed and updates the invoice preview', async ({ page }, testInfo) => {
  await loginToDashboard(page);
  await openSeededInvoice(page);

  if (isVisualValidationRun) {
    const removeAction = page.getByRole('button', { name: 'Remove from invoice' }).first();
    const addPaymentButton = page.getByRole('button', { name: 'Add payment' }).first();

    if (!(await removeAction.isVisible().catch(() => false))) {
      if (await addPaymentButton.isVisible().catch(() => false)) {
        await ensureAppliedPayment(page, testInfo);
      } else {
        await captureCheckpointScreenshot(page, testInfo, 'invoice-payment-actions-full-page', { fullPage: true });
        return;
      }
    }

    const paymentRows = page.locator('tbody tr').filter({ has: page.getByRole('button', { name: 'Remove from invoice' }) });
    await expect(paymentRows.first()).toBeVisible();
    await captureCheckpointScreenshot(page, testInfo, 'invoice-payment-actions-full-page', { fullPage: true });
    return;
  }

  await ensureAppliedPayment(page, testInfo);

  const paymentRows = page.locator('tbody tr').filter({ has: page.getByRole('button', { name: 'Remove from invoice' }) });
  await expect(paymentRows.first()).toBeVisible();
  await expect(paymentRows.first()).toContainText(/\d+\.\d{2} €/);
  await expect(page.getByRole('button', { name: 'Remove from invoice' }).first()).toBeVisible();

  await captureCheckpointScreenshot(page, testInfo, 'invoice-payment-actions-full-page', { fullPage: true });
  await captureCheckpointScreenshot(page, testInfo, 'invoice-payment-remove-before-full-page', { fullPage: true });

  const beforePaymentRowCount = await paymentRows.count();
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Remove this payment from this invoice?');
    await dialog.dismiss();
  });
  await page.getByRole('button', { name: 'Remove from invoice' }).first().click();

  await expect(paymentRows).toHaveCount(beforePaymentRowCount);
  await expect(page.getByRole('button', { name: 'Remove from invoice' }).first()).toBeVisible();

  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('Remove this payment from this invoice?');
    await dialog.accept();
  });
  await page.getByRole('button', { name: 'Remove from invoice' }).first().click();
  await page.waitForURL(/\/invoices\/\d+\/\?tab=preview$/);

  await expect(paymentRows).toHaveCount(beforePaymentRowCount - 1);
  await expect(page.getByRole('button', { name: 'Remove from invoice' })).toHaveCount(beforePaymentRowCount - 1);
  await expect(page.locator('#invoice-preview-frame')).toBeVisible();

  await captureCheckpointScreenshot(page, testInfo, 'invoice-payment-remove-after-full-page', { fullPage: true });
});
