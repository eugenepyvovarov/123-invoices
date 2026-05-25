const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

async function capture(page, testInfo, name) {
  await captureCheckpointScreenshot(page, testInfo, name, { fullPage: true });
}

test.describe('incoming invoice inbox', () => {
  test('reviews seeded candidates and converts a paid invoice', async ({ page }, testInfo) => {
    await loginToDashboard(page);

    const target = process.env.OPENCODE_VISUAL_VALIDATION_TARGET || 'current';
    if (target === 'baseline') {
      await page.goto('/expenses/');
      await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible();
      for (const name of [
        'incoming-inbox-list',
        'incoming-candidate-review',
        'incoming-reviewed-unpaid',
        'incoming-conversion-form',
        'incoming-converted-expense',
      ]) {
        await capture(page, testInfo, name);
      }
      return;
    }

    await expect(page.getByTestId('incoming-inbox-nav')).toBeVisible();
    await page.getByTestId('incoming-inbox-nav').click();
    await expect(page.getByTestId('incoming-inbox-list')).toBeVisible();
    await expect(page.getByText('Invoice E2E-ALPHA-ATT-001')).toBeVisible();
    await capture(page, testInfo, 'incoming-inbox-list');
    await capture(page, testInfo, 'incoming-inbox-mixed-candidates');

    await page.getByTestId('incoming-source-settings-link').click();
    await expect(page.getByTestId('incoming-source-settings')).toBeVisible();
    await expect(page.getByText('INBOX.Invoices')).toBeVisible();
    await capture(page, testInfo, 'incoming-source-seeded');

    await page.goto('/expenses/incoming/');
    await page.getByTestId('incoming-candidate-row').filter({ hasText: 'Invoice E2E-ALPHA-ATT-001' }).getByRole('link', { name: 'Review' }).click();
    await expect(page.getByTestId('incoming-candidate-review')).toBeVisible();
    await expect(page.getByTestId('incoming-artifact-row').first()).toBeVisible();
    await capture(page, testInfo, 'incoming-candidate-review');

    await page.goto('/expenses/incoming/');
    await page.getByTestId('incoming-candidate-row').filter({ hasText: 'Receipt E2E-ALPHA-BODY-002' }).getByRole('link', { name: 'Review' }).click();
    await expect(page.getByText('Email body PDF')).toBeVisible();
    await capture(page, testInfo, 'incoming-body-pdf-artifact');

    await page.goto('/expenses/incoming/?status=reviewed_unpaid');
    await page.getByRole('link', { name: 'Review' }).first().click();
    await expect(page.getByTestId('incoming-reviewed-unpaid')).toBeVisible();
    await expect(page.getByText('no accounting record', { exact: false })).toBeVisible();
    await capture(page, testInfo, 'incoming-reviewed-unpaid');

    await page.goto('/expenses/incoming/?status=ready');
    await page.getByRole('link', { name: 'Review' }).first().click();
    await page.getByTestId('incoming-convert-link').click();
    await expect(page.getByTestId('incoming-conversion-form')).toBeVisible();
    await page.getByLabel('Vendor').fill('Synthetic Supplies Ltd');
    await page.getByLabel('Description').fill('Converted incoming invoice evidence');
    await page.getByLabel('Amount').fill('123.45');
    await page.getByLabel('Currency').fill('EUR');
    await page.getByLabel('Paid date').fill('2026-05-25');
    await capture(page, testInfo, 'incoming-conversion-form');
    await page.getByRole('button', { name: 'Confirm' }).click();
    await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible();
    await expect(page.getByText('Converted incoming invoice evidence')).toBeVisible();
    await page.locator('tr', { hasText: 'Converted incoming invoice evidence' }).getByRole('link', { name: /^#/ }).click();
    await expect(page.getByText('Current file:', { exact: false })).toBeVisible();
    await capture(page, testInfo, 'incoming-converted-expense');

    await page.goto('/expenses/incoming/?status=needs_review');
    await expect(page.getByText('Invoice for shared services')).toBeVisible();
    await capture(page, testInfo, 'incoming-uncertain-needs-review');
  });
});
