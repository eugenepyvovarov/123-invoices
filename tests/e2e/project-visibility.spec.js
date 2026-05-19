const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const TRANSACTION_BACKED_PROJECT = 'Smoke Website Retainer';
const TRANSACTIONLESS_PROJECT_CODE = 'E2E-ZERO-TXN';
const TRANSACTIONLESS_PROJECT_TITLE = 'Transactionless Preview Project';
const TRANSACTIONLESS_PROJECT_LABEL = `${TRANSACTIONLESS_PROJECT_CODE} — ${TRANSACTIONLESS_PROJECT_TITLE}`;
const CUSTOMER_NAME = 'E2E Client Northwind';

async function gotoActiveAllTimeProjects(page) {
  await page.goto('/projects/?date_range=all&project_status=active');
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
}

async function ensureTransactionlessProject(page) {
  await gotoActiveAllTimeProjects(page);

  if (await page.getByRole('link', { name: TRANSACTIONLESS_PROJECT_TITLE }).isVisible().catch(() => false)) {
    return;
  }

  await page.getByRole('link', { name: 'New project' }).click();
  await expect(page.getByRole('heading', { name: 'New project' })).toBeVisible();

  await page.getByLabel('Title').fill(TRANSACTIONLESS_PROJECT_TITLE);
  await page.getByLabel('Project code').fill(TRANSACTIONLESS_PROJECT_CODE);
  await page.getByLabel('Customer').selectOption({ label: CUSTOMER_NAME });
  await page.getByRole('button', { name: 'Save project' }).click();

  if (!/\/projects\/\d+\/?$/.test(page.url())) {
    await expect(page.getByRole('link', { name: TRANSACTIONLESS_PROJECT_TITLE })).toBeVisible();
    await page.getByRole('link', { name: TRANSACTIONLESS_PROJECT_TITLE }).click();
  }
  await expect(page).toHaveURL(/\/projects\/\d+\/?$/);
  await expect(page.getByRole('heading', { name: new RegExp(TRANSACTIONLESS_PROJECT_TITLE) })).toBeVisible();
}

test('transactionless project is visible in projects and invoice project selection', async ({ page }, testInfo) => {
  await loginToDashboard(page);
  await ensureTransactionlessProject(page);

  await gotoActiveAllTimeProjects(page);
  await expect(page.getByRole('link', { name: TRANSACTION_BACKED_PROJECT })).toBeVisible();
  await expect(page.getByRole('link', { name: TRANSACTIONLESS_PROJECT_TITLE })).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'projects-list-transactionless-project', {
    fullPage: true,
  });

  await page.goto('/invoices/add/');
  await expect(page.getByRole('heading', { name: 'Invoice details' })).toBeVisible();
  await page.getByLabel('Project').selectOption({ label: TRANSACTIONLESS_PROJECT_LABEL });
  await expect(page.getByLabel('Project')).toHaveValue(/\d+/);
  await expect(page.getByText('No previous items for this project yet.')).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'invoice-form-transactionless-project-selected', {
    fullPage: true,
  });
});
