const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');

const PAYMENT_MEMO = 'Playwright payment drawer smoke test payment.';
const PAYMENT_AMOUNT = '150.00';

test('payment drawer adds a payment and persists it after reload', async ({ page }) => {
  await loginToDashboard(page);

  await page.goto('/projects/');
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
  await page.getByRole('link', { name: 'Smoke Website Retainer' }).click();

  await expect(page.getByRole('heading', { name: /Smoke Website Retainer/ })).toBeVisible();
  await page.locator('[data-tab-group]').getByRole('link', { name: 'Invoices' }).click();

  const outstandingInvoiceRow = page
    .locator('tbody tr')
    .filter({ has: page.getByRole('link', { name: /#/ }) })
    .filter({ hasText: '400.00 €' })
    .first();

  await expect(outstandingInvoiceRow).toBeVisible();
  await outstandingInvoiceRow.getByRole('link').first().click();

  await expect(page.getByRole('heading', { level: 1, name: /Invoice/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add payment' }).first()).toBeVisible();

  await page.getByRole('button', { name: 'Add payment' }).first().click();
  await expect(page.getByTestId('payment-drawer')).toHaveAttribute('data-drawer-state', 'open');
  await expect(page.getByTestId('payment-form')).toHaveAttribute('data-submit-state', 'idle');

  await expect(page.getByTestId('payment-amount-input')).toHaveValue('400.00');
  await expect(page.getByTestId('payment-apply-invoice').first()).toBeChecked();
  await page.getByTestId('payment-amount-input').fill(PAYMENT_AMOUNT);
  await page.getByTestId('payment-memo-input').fill(PAYMENT_MEMO);
  await page.getByTestId('payment-submit').click();

  await page.waitForURL(/\/invoices\/\d+\/?(?:\?tab=preview)?$/);
  const paymentRow = page.locator('tbody tr').filter({ hasText: PAYMENT_MEMO });
  await expect(paymentRow).toContainText('150.00 €');
  await expect(page.locator('tr.text-muted')).toContainText('250.00 €');
});
