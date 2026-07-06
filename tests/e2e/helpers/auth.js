const fs = require('fs');
const path = require('path');

const { expect } = require('@playwright/test');

const { totp } = require('./totp');

const E2E_EMAIL = process.env.E2E_SMOKE_EMAIL || 'e2e-smoke@example.com';
const E2E_PASSWORD = process.env.E2E_SMOKE_PASSWORD || 'smoke-test-password';
const E2E_TOTP_SECRET = process.env.E2E_SMOKE_TOTP_SECRET || 'JBSWY3DPEHPK3PXP';
const E2E_DEFAULT_COMPANY = process.env.E2E_SMOKE_DEFAULT_COMPANY || 'E2E Smoke Alpha LLC';
const E2E_RECOVERY_CODES = (process.env.E2E_SMOKE_RECOVERY_CODES
  || process.env.E2E_SMOKE_RECOVERY_CODE
  || 'SMOKE00001,SMOKE00002,SMOKE00003,SMOKE00004,SMOKE00005,SMOKE00006,SMOKE00007,SMOKE00008,SMOKE00009,SMOKE00010,SMOKE00011,SMOKE00012,SMOKE00013,SMOKE00014,SMOKE00015,SMOKE00016,SMOKE00017,SMOKE00018,SMOKE00019,SMOKE00020,SMOKE00021,SMOKE00022,SMOKE00023,SMOKE00024')
  .split(',')
  .map((code) => code.trim())
  .filter(Boolean);
const TOTP_STEP_MS = 30_000;
const TOTP_MIN_LIFETIME_MS = 5_000;
const TOTP_RETRY_BUFFER_MS = 1_000;
const OTP_REDIRECT_TIMEOUT_MS = 5_000;
const POST_LOGIN_TIMEOUT_MS = 15_000;
const NAVIGATION_OPTIONS = { waitUntil: 'domcontentloaded', timeout: 30_000 };
const RECOVERY_CODE_STATE_PATH = process.env.PLAYWRIGHT_RECOVERY_CODE_STATE_PATH
  || path.join(process.cwd(), 'tmp', 'playwright-recovery-code-index.txt');

async function gotoWithRetry(page, url, options = {}) {
  const navigationOptions = { ...NAVIGATION_OPTIONS, ...options };
  let lastError = null;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      await page.goto(url, navigationOptions);
      return;
    } catch (error) {
      lastError = error;
      if (attempt === 2) {
        break;
      }
      await page.waitForTimeout(500 * (attempt + 1));
    }
  }

  throw lastError;
}

function msUntilNextTotpStep(now = Date.now()) {
  return TOTP_STEP_MS - (now % TOTP_STEP_MS);
}

async function waitForFreshTotpWindow(page) {
  const msRemaining = msUntilNextTotpStep();

  if (msRemaining <= TOTP_MIN_LIFETIME_MS) {
    await page.waitForTimeout(msRemaining + TOTP_RETRY_BUFFER_MS);
  }
}

async function expectDashboard(page, options = {}) {
  await expect
    .poll(() => new URL(page.url()).pathname, options)
    .toMatch(/^\/(?:dashboard\/)?$/);
}

async function expectSignedInAppShell(page) {
  const dashboardHeading = page.getByRole('heading', { name: 'Dashboard' });
  const activeCompanyName = page.getByTestId('company-switcher-active-name');
  const accountSidebar = page.locator('.sidebar__meta').filter({
    has: page.locator('.sidebar__meta-title', { hasText: 'Account' }),
  });
  const loginForm = page.getByTestId('login-form');
  const otpForm = page.getByTestId('otp-totp-form');

  if (await dashboardHeading.isVisible().catch(() => false)) {
    await expect(dashboardHeading).toBeVisible();
    return;
  }

  if (await activeCompanyName.isVisible().catch(() => false)) {
    await expect(activeCompanyName).toBeVisible();
    return;
  }

  if (await accountSidebar.isVisible().catch(() => false)) {
    await expect(accountSidebar).toBeVisible();
    return;
  }

  await expect(loginForm).toHaveCount(0);
  await expect(otpForm).toHaveCount(0);
}

function isDashboardPath(url) {
  return new URL(url).pathname.match(/^\/(?:dashboard\/)?$/);
}

function isOtpVerifyPath(url) {
  return new URL(url).pathname.match(/^\/accounts\/login\/verify\/?$/);
}

function isLoginPath(url) {
  return new URL(url).pathname.match(/^\/accounts\/login\/?$/);
}

function nextRecoveryCode() {
  const stateDirectory = path.dirname(RECOVERY_CODE_STATE_PATH);
  fs.mkdirSync(stateDirectory, { recursive: true });

  const recoveryCodeIndex = fs.existsSync(RECOVERY_CODE_STATE_PATH)
    ? Number.parseInt(fs.readFileSync(RECOVERY_CODE_STATE_PATH, 'utf8').trim(), 10) || 0
    : 0;
  const recoveryCode = E2E_RECOVERY_CODES[recoveryCodeIndex];

  if (!recoveryCode) {
    throw new Error('No E2E smoke recovery codes remain for Playwright login fallback.');
  }

  fs.writeFileSync(RECOVERY_CODE_STATE_PATH, `${recoveryCodeIndex + 1}`);
  return recoveryCode;
}

async function loginWithRecoveryCode(page) {
  await page.getByLabel('Recovery code').fill(nextRecoveryCode());
  await page.getByTestId('otp-recovery-submit').click();
  await expectDashboard(page, { timeout: POST_LOGIN_TIMEOUT_MS });
}

async function ensureActiveCompany(page, companyName) {
  if (!companyName) {
    return;
  }

  const activeCompanyName = page.getByTestId('company-switcher-active-name');
  if (!(await activeCompanyName.isVisible().catch(() => false))) {
    return;
  }

  if ((await activeCompanyName.textContent())?.trim() === companyName) {
    return;
  }

  await page.getByTestId('company-switcher-toggle').click();
  await page.getByTestId('company-switcher-option').filter({ hasText: companyName }).click();
  await expect(activeCompanyName).toHaveText(companyName);
}

async function loginToDashboard(page, options = {}) {
  const companyName = options.companyName ?? E2E_DEFAULT_COMPANY;

  if (isDashboardPath(page.url())) {
    await expectSignedInAppShell(page);
    await ensureActiveCompany(page, companyName);
    return;
  }

  if (!isLoginPath(page.url()) && !isOtpVerifyPath(page.url())) {
    await gotoWithRetry(page, '/accounts/login/');
  }

  if (isDashboardPath(page.url())) {
    await expectSignedInAppShell(page);
    await ensureActiveCompany(page, companyName);
    return;
  }

  if (isLoginPath(page.url())) {
    await expect(page.getByTestId('login-form')).toBeVisible();
    await page.getByLabel('Email').fill(E2E_EMAIL);
    await page.getByLabel('Password').fill(E2E_PASSWORD);
    await page.getByTestId('login-submit').click();

    if (isDashboardPath(page.url())) {
      await expectSignedInAppShell(page);
      await ensureActiveCompany(page, companyName);
      return;
    }
  }

  await expect(page).toHaveURL(/\/accounts\/login\/verify\/?$/);
  await expect(page.getByTestId('otp-totp-form')).toBeVisible();

  let loggedIn = false;

  for (let attempt = 0; attempt < 3; attempt += 1) {
    await waitForFreshTotpWindow(page);
    await page.getByLabel('Authenticator code').fill(totp(E2E_TOTP_SECRET));
    await page.getByTestId('otp-totp-submit').click();

    try {
      await expectDashboard(page, { timeout: OTP_REDIRECT_TIMEOUT_MS });
      loggedIn = true;
      break;
    } catch (error) {
      if (!isOtpVerifyPath(page.url())) {
        throw error;
      }

      if (attempt < 2) {
        await page.waitForTimeout(msUntilNextTotpStep() + TOTP_RETRY_BUFFER_MS);
      }
    }
  }

  if (!loggedIn) {
    if (isOtpVerifyPath(page.url())) {
      await loginWithRecoveryCode(page);
      loggedIn = true;
    } else {
      await expectDashboard(page, { timeout: POST_LOGIN_TIMEOUT_MS });
      loggedIn = true;
    }
  }

  if (loggedIn) {
    await expectDashboard(page, { timeout: POST_LOGIN_TIMEOUT_MS });
  }
  await expectSignedInAppShell(page);
  await ensureActiveCompany(page, companyName);
}

module.exports = {
  ensureActiveCompany,
  gotoWithRetry,
  loginToDashboard,
};
