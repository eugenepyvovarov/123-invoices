const { test, expect } = require('@playwright/test');

const { ensureActiveCompany, loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const isVisualBaseline = process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline';

async function openCompanySettings(page, companyName) {
  await ensureActiveCompany(page, companyName);
  await page.goto('/company/');
  await expect(page.getByRole('heading', { name: 'Company information' })).toBeVisible();
}

async function saveCompanySettings(page) {
  await page.getByRole('button', { name: 'Save changes' }).click();
  await expect(page.getByRole('heading', { name: 'Company information' })).toBeVisible();
}

async function configureSpanishSifSettings(page) {
  await openCompanySettings(page, 'E2E Smoke Alpha LLC');

  await page.getByLabel('VAT number').fill('00000000T');
  await page.getByLabel('Issuer tax country').selectOption('ES');
  await saveCompanySettings(page);

  await expect(page.getByTestId('spanish-sif-readiness')).toContainText('VERI*FACTU is optional');
  await expect(page.getByLabel('SIF mode')).toContainText('VERI*FACTU');
  await expect(page.getByLabel('SIF mode')).toContainText('No VERI*FACTU');

  await page.getByLabel('Enable Spanish SIF compliance for this issuer').check();
  await page.getByLabel('SIF mode').selectOption('NO_VERI_FACTU');
  await page.getByLabel('Readiness deadline').selectOption('CORPORATE');
  await page.getByLabel('Operational readiness').selectOption('READY');
  await page.getByLabel('Software name').fill('Lifeisgoodlabs Invoices');
  await page.getByLabel('Software version').fill('2026.07-sif-foundation');
  await page.getByLabel('Software code').fill('LIG-INVOICES');
  await page.getByLabel('Certificate reference').fill('Preview non-secret certificate label');
  await saveCompanySettings(page);

  await expect(page.getByTestId('spanish-sif-readiness')).toBeVisible();
  await expect(page.getByText('Deadline: 2027-01-01')).toBeVisible();
  await expect(page.getByLabel('Enable Spanish SIF compliance for this issuer')).toBeChecked();
  await expect(page.getByLabel('SIF mode')).toHaveValue('NO_VERI_FACTU');
}

async function verifyNonSpanishGuardrails(page) {
  await openCompanySettings(page, 'E2E Smoke Beta LLC');
  await expect(page.getByTestId('issuer-sif-settings-section')).toBeVisible();
  await expect(page.getByTestId('non-spanish-no-sif-warning')).toContainText('No Spanish SIF warnings');
  await expect(page.getByTestId('spanish-sif-warning')).toHaveCount(0);
  await expect(page.getByLabel('Enable Spanish SIF compliance for this issuer')).toHaveCount(0);
  await expect(page.getByLabel('SIF mode')).toHaveCount(0);
}

test('Spanish SIF settings readiness and non-Spanish guardrails', async ({ page }, testInfo) => {
  await loginToDashboard(page);

  if (isVisualBaseline) {
    await openCompanySettings(page, 'E2E Smoke Alpha LLC');
    await captureCheckpointScreenshot(page, testInfo, 'spanish-issuer-sif-settings', { fullPage: true });

    await openCompanySettings(page, 'E2E Smoke Beta LLC');
    await captureCheckpointScreenshot(page, testInfo, 'non-spanish-issuer-settings', { fullPage: true });
    return;
  }

  await configureSpanishSifSettings(page);
  await captureCheckpointScreenshot(page, testInfo, 'spanish-sif-readiness', { fullPage: true });
  await captureCheckpointScreenshot(page, testInfo, 'spanish-issuer-sif-settings', { fullPage: true });

  await verifyNonSpanishGuardrails(page);
  await captureCheckpointScreenshot(page, testInfo, 'non-spanish-normal-settings', { fullPage: true });
  await captureCheckpointScreenshot(page, testInfo, 'non-spanish-issuer-settings', { fullPage: true });
});
