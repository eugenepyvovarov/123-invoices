const path = require('path');
const { execFileSync } = require('child_process');

const { test, expect } = require('@playwright/test');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const E2E_EMAIL = process.env.E2E_SMOKE_EMAIL || 'e2e-smoke@example.com';
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const PYTHON_BIN = process.env.PYTHON_BIN || 'python3';

function promoteSmokeUserToSuperuser() {
  execFileSync(
    PYTHON_BIN,
    [
      'manage.py',
      'shell',
      '-c',
      [
        'from django.contrib.auth import get_user_model',
        `User = get_user_model()`,
        `user = User.objects.get(email=${JSON.stringify(E2E_EMAIL)})`,
        'user.is_staff = True',
        'user.is_superuser = True',
        "user.save(update_fields=['is_staff', 'is_superuser'])",
      ].join('; '),
    ],
    {
      cwd: REPO_ROOT,
      env: process.env,
      stdio: 'pipe',
    },
  );
}

test.use({ video: 'on' });

test('superuser account sidebar keeps backups aligned with logout and opens backup settings', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1200 });

  if (!process.env.OPENCODE_PREVIEW_PUBLIC_URL) {
    promoteSmokeUserToSuperuser();
  }

  await page.goto('/dashboard/');
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

  const accountSection = page.locator('.sidebar__meta').filter({
    has: page.locator('.sidebar__meta-title', { hasText: 'Account' }),
  });
  const backupAction = accountSection.getByRole('link', { name: 'Backups' });
  const logoutAction = accountSection.getByRole('button', { name: 'Logout' });
  const backupLabel = backupAction.locator('.sidebar__account-action-label');
  const logoutLabel = logoutAction.locator('.sidebar__account-action-label');

  await expect(accountSection).toBeVisible();
  await expect(backupAction).toBeVisible();
  await expect(logoutAction).toBeVisible();
  await expect(backupAction.locator('svg.icon-tabler-database-export')).toBeVisible();
  await expect(logoutAction.locator('svg.icon-tabler-logout')).toBeVisible();

  const [backupStyles, logoutStyles] = await Promise.all([
    backupLabel.evaluate((element) => {
      const styles = window.getComputedStyle(element);
      const buttonStyles = window.getComputedStyle(element.closest('.sidebar__account-action'));

      return {
        fontSize: styles.fontSize,
        fontWeight: styles.fontWeight,
        lineHeight: styles.lineHeight,
        buttonMinHeight: buttonStyles.minHeight,
        buttonPaddingTop: buttonStyles.paddingTop,
        buttonPaddingRight: buttonStyles.paddingRight,
        buttonPaddingBottom: buttonStyles.paddingBottom,
        buttonPaddingLeft: buttonStyles.paddingLeft,
      };
    }),
    logoutLabel.evaluate((element) => {
      const styles = window.getComputedStyle(element);
      const buttonStyles = window.getComputedStyle(element.closest('.sidebar__account-action'));

      return {
        fontSize: styles.fontSize,
        fontWeight: styles.fontWeight,
        lineHeight: styles.lineHeight,
        buttonMinHeight: buttonStyles.minHeight,
        buttonPaddingTop: buttonStyles.paddingTop,
        buttonPaddingRight: buttonStyles.paddingRight,
        buttonPaddingBottom: buttonStyles.paddingBottom,
        buttonPaddingLeft: buttonStyles.paddingLeft,
      };
    }),
  ]);

  expect(backupStyles).toEqual(logoutStyles);
  expect(backupStyles).toMatchObject({
    fontSize: '14px',
    fontWeight: '600',
    buttonMinHeight: '48px',
    buttonPaddingTop: '8px',
    buttonPaddingRight: '14px',
    buttonPaddingBottom: '8px',
    buttonPaddingLeft: '14px',
  });

  await captureCheckpointScreenshot(accountSection, testInfo, 'account-sidebar-actions-compact');

  const accountActions = accountSection.locator('.sidebar__account-action');
  await expect(accountActions).toHaveCount(2);
  await captureCheckpointScreenshot(accountSection, testInfo, 'account-sidebar-buttons-aligned');

  await backupAction.click();

  await expect(page).toHaveURL(/\/backup-settings\/?$/);
  await expect(page.getByRole('heading', { name: 'Backup settings' })).toBeVisible();
  await captureCheckpointScreenshot(page.locator('main'), testInfo, 'backup-settings-destination');
});
