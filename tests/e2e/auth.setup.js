const { test } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');

const AUTH_STATE_PATH = process.env.PLAYWRIGHT_AUTH_STATE_PATH || 'tmp/playwright-auth-state.json';

test('authenticate smoke user', async ({ page }) => {
  test.skip(
    process.env.OPENCODE_DEMO_SCENARIO === 'production-host-runtime-reachable',
    'Production host runtime evidence does not depend on seeded authenticated data.',
  );

  await loginToDashboard(page);
  await page.context().storageState({ path: AUTH_STATE_PATH });
});
