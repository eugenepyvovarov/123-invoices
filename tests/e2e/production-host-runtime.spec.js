const { test, expect } = require('@playwright/test');

const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

test('production host runtime accepts configured review host', async ({ page }, testInfo) => {
  const response = await page.goto('/', { waitUntil: 'domcontentloaded' });

  expect(response, 'app root should return an HTTP response').not.toBeNull();
  expect(response.status(), 'configured host should not be rejected').not.toBe(400);

  await page.waitForLoadState('networkidle').catch(() => {});
  await captureCheckpointScreenshot(page, testInfo, 'host-contract-accepted', { fullPage: true });
});
