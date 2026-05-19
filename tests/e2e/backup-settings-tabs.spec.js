const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const isVisualValidationRun = Boolean(process.env.OPENCODE_VISUAL_VALIDATION_FULL_PAGE_CHECKPOINTS);

async function panelIsActive(panel) {
  return panel.evaluate((element) => element.classList.contains('is-active')).catch(() => false);
}

async function ensureBackupSettingsTabActive(backupSettingsTab, backupSettingsPanel) {
  if (!(await panelIsActive(backupSettingsPanel))) {
    await backupSettingsTab.click();
  }
  await expect(backupSettingsPanel).toHaveClass(/is-active/);
}

async function submitAndWaitForSettledPage(page, button) {
  const postResponse = page
    .waitForResponse((response) => response.url().includes('/backup-settings/') && response.request().method() === 'POST')
    .catch(() => null);
  await button.click();
  await Promise.race([
    postResponse,
    page.waitForLoadState('networkidle').catch(() => null),
  ]);
  await page.waitForLoadState('networkidle').catch(() => null);
}

function collectNonEmptyCellTexts(values) {
  return values
    .map((value) => value.replace(/\s+/g, ' ').trim())
    .filter(Boolean)
    .filter((value) => value !== '—');
}

test.use({ video: 'on' });

test('superuser backup settings keeps ajax interactions local to the settings tab', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1200 });

  await loginToDashboard(page);
  await page.goto('/backup-settings/');

  await expect(page).toHaveURL(/\/backup-settings\/?$/);

  const tabs = page.locator('[data-backup-settings-tabs]');
  const recentBackupsTab = tabs.getByRole('link', { name: 'Recent backups' });
  const backupSettingsTab = tabs.getByRole('link', { name: 'Backup settings' });
  const recentBackupsPanel = page.locator('#recent-backups-panel');
  const backupSettingsPanel = page.locator('#backup-settings-panel');
  const recentBackupsHeading = recentBackupsPanel.getByRole('heading', { name: 'Recent backups' });
  const recentBackupsTable = recentBackupsPanel.locator('table');
  const recentBackupsSurface = page.locator('[data-backup-settings-tabs]');
  const successfulRecentBackupRow = recentBackupsPanel.locator('tbody tr').filter({
    has: page.locator('.backup-status-indicator[aria-label="Succeeded"]'),
  }).first();
  const deterministicFailedRecentBackupRow = recentBackupsPanel.locator('tbody tr').filter({
    has: page.locator('.backup-status-indicator[aria-label="Failed"]'),
  }).filter({
    hasText: /Apr 17[\s\S]*08:30/,
  }).first();

  if (isVisualValidationRun) {
    const visualSuccessfulRecentBackupRow = recentBackupsPanel.locator('tbody tr').filter({ hasText: /Succeeded/ }).first();
    const visualFailedRecentBackupRow = recentBackupsPanel.locator('tbody tr').filter({ hasText: /Failed/ }).first();

    await page.waitForLoadState('networkidle').catch(() => null);
    await expect(recentBackupsTable).toBeVisible();
    await expect(visualSuccessfulRecentBackupRow).toBeVisible();
    await expect(visualFailedRecentBackupRow).toBeVisible();
    await captureCheckpointScreenshot(page, testInfo, 'backup-settings-recent-backups-table-full-page', { fullPage: true });
    return;
  }

  await expect(page.getByRole('heading', { name: 'Backup settings' })).toBeVisible();
  const runBackupNowButton = recentBackupsPanel.getByRole('button', { name: 'Run backup now' });
  const recentBackupsHeader = recentBackupsHeading.locator('xpath=ancestor::div[contains(@class, "d-flex")][1]');
  const recentBackupRows = recentBackupsTable.locator('tbody tr');
  const sizeLinks = recentBackupsPanel.locator('tbody a[href*="/download/"]');
  const viewDetailsLinks = recentBackupsPanel.getByRole('link', { name: 'View details' });
  const statusCells = recentBackupsPanel.locator('tbody td[data-label="Status"]');

  await expect(tabs).toBeVisible();
  await expect(recentBackupsTab).toHaveClass(/is-active/);
  await expect(backupSettingsTab).not.toHaveClass(/is-active/);
  await expect(recentBackupsPanel).toHaveClass(/is-active/);
  await expect(backupSettingsPanel).not.toHaveClass(/is-active/);
  await expect(recentBackupsHeading).toBeVisible();
  await expect(runBackupNowButton).toBeVisible();
  await expect(recentBackupsPanel.locator('form.mb-0')).toHaveAttribute('action', /\/backup-settings\/run-now\/?$/);
  await expect(page.getByText('Next scheduled backup')).toHaveCount(0);
  await expect(page.getByText('Last run')).toHaveCount(0);

  const [headerBox, buttonBox] = await Promise.all([
    recentBackupsHeader.boundingBox(),
    runBackupNowButton.boundingBox(),
  ]);

  expect(headerBox).not.toBeNull();
  expect(buttonBox).not.toBeNull();
  expect(buttonBox.x).toBeGreaterThan(headerBox.x + (headerBox.width * 0.45));

  await captureCheckpointScreenshot(page, testInfo, 'backup-settings-recent-backups-table-full-page', { fullPage: true });

  await expect(recentBackupsTable).toBeVisible();
  await expect(successfulRecentBackupRow).toBeVisible();
  await expect(deterministicFailedRecentBackupRow).toBeVisible();
  const recentBackupRowCount = await recentBackupRows.count();
  const startedTexts = collectNonEmptyCellTexts(await recentBackupsPanel.locator('tbody td[data-label="Started"]').allTextContents());
  const finishedTexts = collectNonEmptyCellTexts(await recentBackupsPanel.locator('tbody td[data-label="Finished"]').allTextContents());
  const successfulDownloadLink = successfulRecentBackupRow.locator('a[href*="/download/"]');
  const failedViewDetailsLink = deterministicFailedRecentBackupRow.getByRole('link', { name: 'View details' });

  expect(recentBackupRowCount).toBeGreaterThanOrEqual(5);
  await expect(recentBackupsTable.getByRole('columnheader', { name: 'Object key' })).toHaveCount(0);
  await expect(recentBackupsTable.getByRole('columnheader', { name: 'Error' })).toHaveCount(0);
  expect(startedTexts.some((value) => /\b\d{2}:\d{2}\b/.test(value))).toBeTruthy();
  expect(startedTexts.some((value) => /\b\d{4}\b/.test(value))).toBeTruthy();
  expect(startedTexts.some((value) => !/\b\d{4}\b/.test(value))).toBeTruthy();
  expect(startedTexts.every((value) => !/\b(?:am|pm)\b/i.test(value))).toBeTruthy();
  expect(finishedTexts.some((value) => /\b\d{2}:\d{2}\b/.test(value))).toBeTruthy();
  expect(finishedTexts.some((value) => /\b\d{4}\b/.test(value))).toBeTruthy();
  expect(finishedTexts.some((value) => !/\b\d{4}\b/.test(value))).toBeTruthy();
  expect(finishedTexts.every((value) => !/\b(?:am|pm)\b/i.test(value))).toBeTruthy();
  expect(await sizeLinks.count()).toBeGreaterThan(0);
  expect(await viewDetailsLinks.count()).toBeGreaterThan(0);
  expect(await statusCells.locator('.icon-tabler-circle-check').count()).toBeGreaterThan(0);
  expect(await statusCells.locator('.icon-tabler-circle-x').count()).toBeGreaterThan(0);
  await expect(successfulRecentBackupRow.locator('.visually-hidden')).toContainText('Succeeded');
  await expect(deterministicFailedRecentBackupRow.locator('.visually-hidden')).toContainText('Failed');
  await expect(deterministicFailedRecentBackupRow.locator('a[href*="/download/"]')).toHaveCount(0);
  await expect(successfulDownloadLink).toHaveCount(1);

  const firstSizeLink = sizeLinks.first();
  const firstViewDetailsLink = viewDetailsLinks.first();

  await expect(firstSizeLink).toHaveAttribute('target', '_blank');
  await expect(firstSizeLink).toHaveAttribute('href', /\/backup-settings\/runs\/\d+\/download\/?$/);
  await expect(firstViewDetailsLink).toHaveClass(/btn/);
  await expect(firstViewDetailsLink).toHaveClass(/btn-outline-secondary/);

  const [tabsBox, tabContainerBox, cardBox] = await Promise.all([
    tabs.boundingBox(),
    tabs.locator('.backup-settings-tab-container').boundingBox(),
    recentBackupsPanel.locator('.drawer-section').first().boundingBox(),
  ]);

  expect(tabsBox).not.toBeNull();
  expect(tabContainerBox).not.toBeNull();
  expect(cardBox).not.toBeNull();
  expect(Math.abs((tabsBox?.x ?? 0) - (tabContainerBox?.x ?? 0))).toBeLessThanOrEqual(2);
  expect(Math.abs(((tabsBox?.x ?? 0) + (tabsBox?.width ?? 0)) - ((tabContainerBox?.x ?? 0) + (tabContainerBox?.width ?? 0)))).toBeLessThanOrEqual(2);
  expect((cardBox?.y ?? 0) - (tabsBox?.y ?? 0)).toBeLessThan(90);

  await captureCheckpointScreenshot(recentBackupsSurface, testInfo, 'backup-settings-recent-backups-tab-surface');
  await captureCheckpointScreenshot(recentBackupsPanel, testInfo, 'backup-settings-recent-backups-table');

  const [downloadPage] = await Promise.all([
    page.context().waitForEvent('page'),
    firstSizeLink.click(),
  ]);
  await expect.poll(() => downloadPage.url()).toMatch(/\/backup-settings\/runs\/\d+\/download\/?$|^https?:\/\//);
  await expect(page).toHaveURL(/\/backup-settings\/?$/);
  await downloadPage.close();

  await Promise.all([
    page.waitForURL(/\/backup-settings\/runs\/\d+\/?$/),
    failedViewDetailsLink.click(),
  ]);
  await expect(page.getByRole('heading', { name: /Backup run/i })).toBeVisible();
  await expect(page.getByText('RuntimeError: upload failed')).toBeVisible();
  await expect(page.locator('dd').filter({ hasText: 'Upload to object storage failed.' })).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'backup-run-detail-from-table');

  await page.goBack();
  await expect(page).toHaveURL(/\/backup-settings\/?$/);
  await expect(recentBackupsPanel).toHaveClass(/is-active/);
  await expect(recentBackupsTable).toBeVisible();

  await backupSettingsTab.click();

  await expect(backupSettingsTab).toHaveClass(/is-active/);
  await expect(recentBackupsTab).not.toHaveClass(/is-active/);
  await expect(backupSettingsPanel).toHaveClass(/is-active/);
  const newConnectionHeading = backupSettingsPanel.getByRole('heading', { name: 'S3 connection' });
  const legacyDestinationHeading = backupSettingsPanel.getByRole('heading', { name: 'Destination' });
  const scheduleHeading = backupSettingsPanel.getByRole('heading', { name: 'Schedule and retention' });
  const newConnectionSection = backupSettingsPanel.locator('[data-backup-settings-destination-section]');
  const hasNewConnectionLayout = await newConnectionHeading.isVisible().catch(() => false);
  const connectionSection = hasNewConnectionLayout ? newConnectionSection : backupSettingsPanel;
  const testConnectionButton = hasNewConnectionLayout
    ? newConnectionSection.getByRole('button', { name: 'Test S3 connection' })
    : backupSettingsPanel.getByRole('button', { name: 'Test S3 connection' });
  const saveChangesButton = backupSettingsPanel.getByRole('button', { name: 'Save changes' });

  await expect(scheduleHeading).toBeVisible();
  await expect(testConnectionButton).toBeVisible();
  await expect(saveChangesButton).toBeVisible();
  if (hasNewConnectionLayout) {
    await expect(newConnectionHeading).toBeVisible();
    await expect(newConnectionSection).toBeVisible();
    await expect(connectionSection.getByRole('button', { name: 'Save changes' })).toHaveCount(0);
  } else {
    await expect(legacyDestinationHeading).toBeVisible();
  }

  const objectPrefixInput = backupSettingsPanel.getByLabel('Object prefix');
  await objectPrefixInput.fill('e2e-demo-updated');
  await recentBackupsTab.click();
  await expect(recentBackupsPanel).toHaveClass(/is-active/);
  await backupSettingsTab.click();
  await expect(objectPrefixInput).toHaveValue('e2e-demo-updated');

  await captureCheckpointScreenshot(connectionSection, testInfo, 'backup-settings-connection-box');
  await captureCheckpointScreenshot(page, testInfo, 'backup-settings-layout-full-page', { fullPage: true });

  const bucketNameInput = backupSettingsPanel.getByLabel('Bucket name');
  await bucketNameInput.fill('');
  if (hasNewConnectionLayout) {
    await page.evaluate(() => {
      window.__backupSettingsAjaxMarker = 'validation-pending';
    });
    await Promise.all([
      page.waitForResponse((response) => response.url().includes('/backup-settings/') && response.request().method() === 'POST'),
      testConnectionButton.click(),
    ]);

    await expect(backupSettingsTab).toHaveClass(/is-active/);
    await expect(recentBackupsTab).not.toHaveClass(/is-active/);
    await expect.poll(() => page.evaluate(() => window.__backupSettingsAjaxMarker)).toBe('validation-pending');
  } else {
    await submitAndWaitForSettledPage(page, testConnectionButton);
    await ensureBackupSettingsTabActive(backupSettingsTab, backupSettingsPanel);
    await expect(recentBackupsTab).not.toHaveClass(/is-active/);
  }
  await expect(page).toHaveURL(/\/backup-settings\/?$/);
  if (hasNewConnectionLayout) {
    const connectionValidationMessage = backupSettingsPanel.getByText('This field is required when backups are enabled.');
    const connectionAlert = connectionSection.getByRole('alert');
    if (await connectionValidationMessage.isVisible().catch(() => false)) {
      await expect(connectionValidationMessage).toBeVisible();
    } else {
      await expect(connectionAlert).toBeVisible();
    }
  } else {
    await expect(backupSettingsPanel).toHaveClass(/is-active/);
    await expect(bucketNameInput).toHaveValue('');
    await expect(testConnectionButton).toBeVisible();
  }

  await captureCheckpointScreenshot(connectionSection, testInfo, 'backup-settings-test-validation');
  await captureCheckpointScreenshot(page, testInfo, 'backup-settings-test-feedback-full-page', { fullPage: true });

  await bucketNameInput.fill('invoices-backups');
  await objectPrefixInput.fill('e2e-demo-ajax-save');
  if (hasNewConnectionLayout) {
    await page.evaluate(() => {
      window.__backupSettingsAjaxMarker = 'save-pending';
    });
    await Promise.all([
      page.waitForResponse((response) => response.url().includes('/backup-settings/') && response.request().method() === 'POST'),
      saveChangesButton.click(),
    ]);

    await expect(backupSettingsTab).toHaveClass(/is-active/);
    await expect(recentBackupsTab).not.toHaveClass(/is-active/);
    await expect.poll(() => page.evaluate(() => window.__backupSettingsAjaxMarker)).toBe('save-pending');
    await expect(backupSettingsPanel.getByRole('alert')).toContainText('Backup settings saved successfully.');
  } else {
    await submitAndWaitForSettledPage(page, saveChangesButton);
    await ensureBackupSettingsTabActive(backupSettingsTab, backupSettingsPanel);
    await expect(recentBackupsTab).not.toHaveClass(/is-active/);
  }
  await expect(page).toHaveURL(/\/backup-settings\/?$/);
  await expect(backupSettingsPanel.getByLabel('Object prefix')).toHaveValue('e2e-demo-ajax-save');

  await captureCheckpointScreenshot(backupSettingsPanel, testInfo, 'backup-settings-save-success');
  await captureCheckpointScreenshot(page, testInfo, 'backup-settings-save-feedback-full-page', { fullPage: true });
});
