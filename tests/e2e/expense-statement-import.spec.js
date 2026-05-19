const fs = require('fs/promises');
const path = require('path');

const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const FIXTURE_DIR = path.join(__dirname, 'fixtures/expense-import');
const CARD_STATEMENT_FIXTURE = path.join(FIXTURE_DIR, 'card-statement.csv');
const WISE_STATEMENT_FIXTURE = path.join(FIXTURE_DIR, 'wise-statement.csv');
const CAIXABANK_XLSX_FIXTURE = path.join(FIXTURE_DIR, 'caixabank-attached.xlsx');
const CAIXABANK_CSV_FIXTURE = path.join(FIXTURE_DIR, 'caixabank-semicolon.csv');
const AI_FIXTURE_BASE_URL = 'https://expense-import-ai-fixture.local';
const AI_FIXTURE_MODEL = 'expense-import-card-mapping-fixture';

async function buildUniqueTextStatement(testInfo, fixturePath, replacements, prefix) {
  const uniqueToken = `${testInfo.retry}-${Date.now()}`;
  let statement = await fs.readFile(fixturePath, 'utf8');

  for (const [source, targetPrefix] of replacements) {
    statement = statement.replaceAll(source, `${targetPrefix}-${uniqueToken}`);
  }

  const outputPath = testInfo.outputPath(`${prefix}-${uniqueToken}${path.extname(fixturePath)}`);
  await fs.writeFile(outputPath, statement, 'utf8');
  return outputPath;
}

async function buildUniqueBinaryStatement(testInfo, fixturePath, prefix) {
  const uniqueToken = `${testInfo.retry}-${Date.now()}`;
  const outputPath = testInfo.outputPath(`${prefix}-${uniqueToken}${path.extname(fixturePath)}`);
  await fs.copyFile(fixturePath, outputPath);
  return outputPath;
}

async function buildUniqueCardStatement(testInfo) {
  return buildUniqueTextStatement(
    testInfo,
    CARD_STATEMENT_FIXTURE,
    [
      ['CARD-FIXTURE-001', 'CARD-E2E-AI-001'],
      ['CARD-FIXTURE-002', 'CARD-E2E-AI-002'],
    ],
    'expense-card-statement',
  );
}

async function buildUniqueWiseStatement(testInfo) {
  return buildUniqueTextStatement(
    testInfo,
    WISE_STATEMENT_FIXTURE,
    [
      ['WISE-FIXTURE-001', 'WISE-E2E-001'],
      ['WISE-FIXTURE-002', 'WISE-E2E-002'],
      ['WISE-FIXTURE-003', 'WISE-E2E-003'],
      ['WISE-REF-001', 'WISE-REF-E2E-001'],
      ['WISE-REF-002', 'WISE-REF-E2E-002'],
      ['WISE-REF-003', 'WISE-REF-E2E-003'],
    ],
    'expense-wise-statement',
  );
}

async function buildUniqueCaixabankCsv(testInfo) {
  return buildUniqueTextStatement(
    testInfo,
    CAIXABANK_CSV_FIXTURE,
    [
      ['I.R.P.F. MOD.111', 'CAIXA-TAX-E2E'],
      ['factura 2026.0765', 'CAIXA-INVOICE-0765-E2E'],
      ['factura 2026.0719', 'CAIXA-INVOICE-0719-E2E'],
      ['C11-GV26', 'CAIXA-C11-E2E'],
      ['G26 Fianza', 'CAIXA-FIANZA-E2E'],
    ],
    'expense-caixabank-semicolon',
  );
}

async function configureFixtureAIProvider(page, testInfo) {
  await page.goto('/accounts/user-settings/');
  await expect(page.getByRole('heading', { name: 'User settings' })).toBeVisible();
  await expect(page.getByTestId('expense-ai-provider-settings')).toBeVisible();

  await page.getByLabel('Provider base URL').fill(AI_FIXTURE_BASE_URL);
  await page.getByLabel('Model name').fill(AI_FIXTURE_MODEL);
  await page.getByLabel('API key', { exact: true }).fill(`sk-e2e-fixture-${testInfo.retry}`);

  await captureCheckpointScreenshot(page, testInfo, 'expense-ai-settings-full-page', { fullPage: true });
  await page.getByRole('button', { name: 'Save AI provider settings' }).click();
  await expect(page.getByText('API key saved', { exact: true })).toBeVisible();
  await expect(page.getByText(/Saved key:/)).toContainText('••••••••');
}

async function openExpenseImportFromList(page, testInfo, options = {}) {
  await page.goto('/expenses/');
  await expect(page.getByRole('heading', { name: 'Expenses' })).toBeVisible();
  await expect(page.getByTestId('expense-import-entry')).toContainText('Import expense statement');
  if (options.captureEntry !== false) {
    await captureCheckpointScreenshot(page, testInfo, 'expense-statement-import-entry-full-page', { fullPage: true });
  }

  await page.getByTestId('expense-import-entry').click();
  await expect(page.getByRole('heading', { name: 'Import expense statement' })).toBeVisible();
  await expect(page.getByTestId('expense-import-upload')).toContainText('CSV, XLS, XLSX, and ZIP');
  if (options.captureUpload !== false) {
    await captureCheckpointScreenshot(page, testInfo, 'expense-statement-import-upload-guidance-full-page', { fullPage: true });
  }
}

test('expense-caixabank-xlsx-import expense-statement-import-visual imports the sanitized spreadsheet fixture', async ({ page }, testInfo) => {
  await loginToDashboard(page);
  await configureFixtureAIProvider(page, testInfo);
  await openExpenseImportFromList(page, testInfo);

  await page.getByTestId('expense-import-file-input').setInputFiles(
    await buildUniqueBinaryStatement(testInfo, CAIXABANK_XLSX_FIXTURE, 'expense-caixabank-attached'),
  );
  await captureCheckpointScreenshot(page, testInfo, 'expense-caixabank-xlsx-upload-full-page', { fullPage: true });
  await page.getByTestId('expense-import-upload-submit').click();

  const mappingReview = page.getByTestId('expense-import-mapping-review');
  await expect(mappingReview).toBeVisible();
  await expect(mappingReview).toContainText('Mapping source: ai');
  await expect(page.locator('#mapping-paid_date')).toHaveValue('Date');
  await expect(page.locator('#mapping-amount')).toHaveValue('Amount');
  await captureCheckpointScreenshot(page, testInfo, 'expense-caixabank-xlsx-mapping-review-full-page', { fullPage: true });

  await page.getByTestId('expense-import-mapping-submit').click();
  const rowSelection = page.getByTestId('expense-import-row-selection');
  await expect(rowSelection).toBeVisible();
  await expect(rowSelection.locator('tbody tr').first()).toContainText('SANITIZED');
  await captureCheckpointScreenshot(page, testInfo, 'expense-caixabank-xlsx-row-selection-full-page', { fullPage: true });

  await page.getByTestId('expense-import-confirm').click();
  const result = page.getByTestId('expense-import-result');
  await expect(result).toBeVisible();
  await expect(result).toContainText('Import complete');
  await captureCheckpointScreenshot(page, testInfo, 'expense-caixabank-xlsx-result-full-page', { fullPage: true });
});

test('expense-caixabank-semicolon-csv-import expense-statement-import-visual imports the localized semicolon fixture', async ({ page }, testInfo) => {
  await loginToDashboard(page);
  await configureFixtureAIProvider(page, testInfo);
  await openExpenseImportFromList(page, testInfo, { captureEntry: false, captureUpload: false });

  await page.getByTestId('expense-import-file-input').setInputFiles(await buildUniqueCaixabankCsv(testInfo));
  await captureCheckpointScreenshot(page, testInfo, 'expense-caixabank-csv-upload-full-page', { fullPage: true });
  await page.getByTestId('expense-import-upload-submit').click();

  const mappingReview = page.getByTestId('expense-import-mapping-review');
  await expect(mappingReview).toBeVisible();
  await expect(mappingReview).toContainText('Mapping source: ai');
  await expect(page.locator('#mapping-paid_date')).toHaveValue('Date');
  await expect(page.locator('#mapping-amount')).toHaveValue('Amount');
  await captureCheckpointScreenshot(page, testInfo, 'expense-caixabank-csv-stable-response-full-page', { fullPage: true });

  await page.getByTestId('expense-import-mapping-submit').click();
  const rowSelection = page.getByTestId('expense-import-row-selection');
  await expect(rowSelection).toBeVisible();
  await expect(rowSelection.locator('tbody tr')).toHaveCount(7);
  await expect(rowSelection).toContainText('1815.00');
  await captureCheckpointScreenshot(page, testInfo, 'expense-caixabank-csv-preview-full-page', { fullPage: true });
});

test('expense-statement-generic-import previews an AI fixture mapping and imports selected card rows', async ({ page }, testInfo) => {
  await loginToDashboard(page);
  await configureFixtureAIProvider(page, testInfo);
  await openExpenseImportFromList(page, testInfo, { captureEntry: false, captureUpload: false });

  await page.getByTestId('expense-import-file-input').setInputFiles(await buildUniqueCardStatement(testInfo));
  await page.getByTestId('expense-import-upload-submit').click();

  const mappingReview = page.getByTestId('expense-import-mapping-review');
  await expect(mappingReview).toBeVisible();
  await expect(mappingReview).toContainText('Mapping source: ai');
  await expect(page.locator('#mapping-paid_date')).toHaveValue('Txn Date');
  await expect(page.locator('#mapping-amount')).toHaveValue('Card Debit');
  await expect(page.locator('#mapping-transaction_id')).toHaveValue('Reference Number');
  await captureCheckpointScreenshot(page, testInfo, 'expense-import-mapping-review-full-page', { fullPage: true });

  await page.locator('#mapping-currency').selectOption('ISO Currency');
  await page.locator('#save-mapping-name').fill(`Playwright card mapping ${testInfo.retry}-${Date.now()}`);
  await page.getByTestId('expense-import-mapping-submit').click();

  const rowSelection = page.getByTestId('expense-import-row-selection');
  await expect(rowSelection).toBeVisible();
  await expect(rowSelection.locator('tbody tr')).toHaveCount(2);
  await rowSelection.locator('[data-expense-import-row]').nth(1).uncheck();
  await captureCheckpointScreenshot(page, testInfo, 'expense-import-row-selection-full-page', { fullPage: true });

  await page.getByTestId('expense-import-confirm').click();
  const result = page.getByTestId('expense-import-result');
  await expect(result).toBeVisible();
  await expect(result).toContainText('Rows: 2');
  await expect(result).toContainText('Created: 1');
  await expect(result).toContainText('Unselected: 1');
  await captureCheckpointScreenshot(page, testInfo, 'expense-import-result-full-page', { fullPage: true });
});

test('expense-statement-wise-global-mapping previews Wise rows without provider calls', async ({ page }, testInfo) => {
  await loginToDashboard(page);
  await openExpenseImportFromList(page, testInfo, { captureEntry: false, captureUpload: false });

  await page.getByTestId('expense-import-file-input').setInputFiles(await buildUniqueWiseStatement(testInfo));
  await page.getByTestId('expense-import-upload-submit').click();

  const mappingReview = page.getByTestId('expense-import-mapping-review');
  await expect(mappingReview).toBeVisible();
  await expect(mappingReview).toContainText('Mapping source: global');
  await expect(mappingReview).toContainText('Wise CSV expense import');
  await captureCheckpointScreenshot(page, testInfo, 'expense-import-wise-global-mapping-full-page', { fullPage: true });

  await page.getByTestId('expense-import-mapping-submit').click();
  const rowSelection = page.getByTestId('expense-import-row-selection');
  await expect(rowSelection).toBeVisible();
  await expect(rowSelection.locator('tbody tr')).toHaveCount(3);
  await expect(rowSelection.locator('[data-expense-import-row]').nth(0)).toBeChecked();
  await expect(rowSelection.locator('[data-expense-import-row]').nth(1)).toBeChecked();
  await expect(rowSelection.locator('[data-expense-import-row]').nth(2)).not.toBeChecked();
  await captureCheckpointScreenshot(page, testInfo, 'expense-import-wise-row-selection-full-page', { fullPage: true });

  await page.getByTestId('expense-import-confirm').click();
  const result = page.getByTestId('expense-import-result');
  await expect(result).toBeVisible();
  await expect(result).toContainText('Rows: 3');
  await expect(result).toContainText('Created: 2');
  await captureCheckpointScreenshot(page, testInfo, 'expense-import-wise-result-full-page', { fullPage: true });
});
