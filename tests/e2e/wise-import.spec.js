const fs = require('fs/promises');
const path = require('path');

const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');

const VALID_STATEMENT_FIXTURE = path.join(__dirname, 'fixtures/wise/valid_statement.csv');
const INVALID_STATEMENT_FIXTURE = path.join(__dirname, 'fixtures/wise/invalid_statement.csv');

async function openGenericExpenseImportFromProject(page) {
  await loginToDashboard(page);

  await page.goto('/projects/');
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
  await page.getByRole('link', { name: 'Smoke Website Retainer' }).click();

  await expect(page.getByRole('heading', { name: /Smoke Website Retainer/ })).toBeVisible();
  await page.getByRole('link', { name: 'Import expense statement' }).click();
  await expect(page.getByRole('heading', { name: 'Import expense statement' })).toBeVisible();
}

async function buildUniqueWiseStatement(testInfo) {
  const uniqueToken = `${testInfo.retry}-${Date.now()}`;
  const statement = (await fs.readFile(VALID_STATEMENT_FIXTURE, 'utf8'))
    .replaceAll('CARD-E2E-001', `CARD-E2E-${uniqueToken}-001`)
    .replaceAll('CARD-E2E-002', `CARD-E2E-${uniqueToken}-002`)
    .replaceAll('SMOKE-REF-001', `SMOKE-REF-${uniqueToken}-001`)
    .replaceAll('SMOKE-REF-002', `SMOKE-REF-${uniqueToken}-002`);

  const outputPath = testInfo.outputPath(`wise-valid-${uniqueToken}.csv`);
  await fs.writeFile(outputPath, statement, 'utf8');
  return outputPath;
}

test('generic expense import uploads a valid Wise statement and shows a success summary', async ({ page }, testInfo) => {
  await openGenericExpenseImportFromProject(page);

  await page.getByTestId('expense-import-file-input').setInputFiles(await buildUniqueWiseStatement(testInfo));
  await page.getByTestId('expense-import-upload-submit').click();

  const mappingReview = page.getByTestId('expense-import-mapping-review');
  await expect(mappingReview).toBeVisible();
  await expect(mappingReview).toContainText('Mapping source: global');
  await expect(mappingReview).toContainText('Wise CSV expense import');

  await page.getByTestId('expense-import-mapping-submit').click();
  const rowSelection = page.getByTestId('expense-import-row-selection');
  await expect(rowSelection).toBeVisible();
  await expect(rowSelection.locator('tbody tr')).toHaveCount(2);

  await page.getByTestId('expense-import-confirm').click();
  const result = page.getByTestId('expense-import-result');
  await expect(result).toBeVisible();
  await expect(result).toContainText('Rows: 2');
  await expect(result).toContainText('Created: 2');
  await expect(result).toContainText('Skipped existing: 0');
});

test('generic expense import shows an inline error for an invalid Wise statement file', async ({ page }) => {
  await openGenericExpenseImportFromProject(page);

  await page.getByTestId('expense-import-file-input').setInputFiles(INVALID_STATEMENT_FIXTURE);
  await page.getByTestId('expense-import-upload-submit').click();

  await expect(page.getByRole('alert')).toHaveText(
    /Import mapping column ".+" for .+ is not present in the statement\./,
  );
});
