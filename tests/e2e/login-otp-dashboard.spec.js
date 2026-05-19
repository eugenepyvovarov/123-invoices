const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');

test('login with OTP reaches the dashboard', async ({ page }) => {
  await loginToDashboard(page);
  await expect(page.getByTestId('company-switcher-active-name')).toHaveText('E2E Smoke Alpha LLC');
});
