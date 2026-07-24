const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

const IS_BASELINE_VISUAL = process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline';

test.use({ storageState: { cookies: [], origins: [] } });

async function openUserSettings(page, viewport = { width: 1600, height: 1200 }) {
  await page.setViewportSize(viewport);
  await loginToDashboard(page);
  await page.goto('/accounts/user-settings/');
  await expect(page.getByRole('heading', { level: 1, name: 'User settings' })).toBeVisible();
}

async function expectIntegrationTabsAreScoped(page) {
  const integrations = page.getByTestId('integrations-settings');
  const apiTab = integrations.getByRole('tab', { name: 'API' });
  const mcpTab = integrations.getByRole('tab', { name: 'MCP' });
  const apiPanel = page.getByTestId('invoices-api-token-settings');
  const mcpPanel = page.getByTestId('mcp-connection-settings');
  const security = page.locator('[data-user-settings-tabs]').filter({ hasText: 'Security' });
  const passwordTab = security.getByRole('tab', { name: 'Password' });
  const otpTab = security.getByRole('tab', { name: 'Two-factor' });

  await expect(apiTab).toHaveClass(/is-active/);
  await expect(apiTab).toHaveAttribute('aria-selected', 'true');
  await expect(apiTab).toHaveAttribute('tabindex', '0');
  await expect(mcpTab).toHaveAttribute('aria-selected', 'false');
  await expect(mcpTab).toHaveAttribute('tabindex', '-1');
  await expect(apiPanel).toBeVisible();
  await expect(mcpPanel).toBeHidden();
  await expect(passwordTab).toHaveClass(/is-active/);

  await mcpTab.click();

  await expect(mcpTab).toHaveClass(/is-active/);
  await expect(mcpTab).toHaveAttribute('aria-selected', 'true');
  await expect(mcpTab).toHaveAttribute('tabindex', '0');
  await expect(apiTab).not.toHaveClass(/is-active/);
  await expect(apiTab).toHaveAttribute('aria-selected', 'false');
  await expect(apiPanel).toBeHidden();
  await expect(mcpPanel).toBeVisible();
  await expect(passwordTab).toHaveClass(/is-active/);
  await expect(otpTab).not.toHaveClass(/is-active/);

  await otpTab.click();
  await expect(otpTab).toHaveClass(/is-active/);
  await expect(mcpTab).toHaveClass(/is-active/);
  await expect(mcpPanel).toBeVisible();
}

test('integration tabs switch independently on desktop and copy public MCP values', async ({ page }) => {
  test.skip(IS_BASELINE_VISUAL, 'Baseline visual-validation targets may not include the API/MCP integration tabs yet.');

  await openUserSettings(page);

  await expectIntegrationTabsAreScoped(page);

  const mcpPanel = page.getByTestId('mcp-connection-settings');
  await expect(mcpPanel.getByLabel('MCP endpoint URL')).toBeVisible();
  await expect(mcpPanel.getByRole('button', { name: 'Copy endpoint' })).toBeVisible();
  await mcpPanel.getByRole('button', { name: 'Copy endpoint' }).click();
  await expect(mcpPanel.getByRole('button', { name: 'Copied' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy endpoint' })).toHaveCount(0);
  await expect(page.getByTestId('api-token-plaintext-reveal')).toHaveCount(0);
});

test('integration tabs remain usable at a narrow viewport', async ({ page }) => {
  test.skip(IS_BASELINE_VISUAL, 'Baseline visual-validation targets may not include the API/MCP integration tabs yet.');

  await openUserSettings(page, { width: 390, height: 900 });

  const integrations = page.getByTestId('integrations-settings');
  const mcpTab = integrations.getByRole('tab', { name: 'MCP' });
  const mcpPanel = page.getByTestId('mcp-connection-settings');

  await expect(integrations.getByRole('tab', { name: 'API' })).toBeVisible();
  await expect(mcpTab).toBeVisible();

  await mcpTab.click();

  await expect(mcpTab).toHaveAttribute('aria-selected', 'true');
  await expect(mcpPanel).toBeVisible();
  await expect(mcpPanel.getByLabel('MCP endpoint URL')).toBeVisible();
  await expect(mcpPanel.getByRole('button', { name: 'Copy endpoint' })).toBeVisible();
});

test('user settings API/MCP tabs demo evidence', async ({ page }, testInfo) => {
  test.skip(
    process.env.OPENCODE_DEMO_SCENARIO !== 'user-settings-api-mcp-tabs',
    'This evidence test only runs for the User settings API/MCP tabs demo scenario.',
  );
  test.skip(IS_BASELINE_VISUAL, 'The demo requires the current API/MCP integration tabs.');

  await openUserSettings(page);

  const integrations = page.getByTestId('integrations-settings');
  const apiTab = integrations.getByRole('tab', { name: 'API' });
  const mcpTab = integrations.getByRole('tab', { name: 'MCP' });
  const apiPanel = page.getByTestId('invoices-api-token-settings');
  const mcpPanel = page.getByTestId('mcp-connection-settings');

  await expect(apiTab).toHaveAttribute('aria-selected', 'true');
  await expect(apiPanel).toBeVisible();
  await expect(apiPanel.getByRole('heading', { name: 'Invoices API tokens' })).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'integrations-api-tab', { fullPage: true });

  await mcpTab.click();
  await expect(mcpTab).toHaveAttribute('aria-selected', 'true');
  await expect(mcpPanel).toBeVisible();
  await expect(mcpPanel.getByLabel('MCP endpoint URL')).toBeVisible();
  await expect(mcpPanel.getByText(/OAuth 2\.1 \+ PKCE/i)).toBeVisible();
  await mcpPanel.getByRole('button', { name: 'Copy endpoint' }).click();
  await expect(mcpPanel.getByRole('button', { name: 'Copied' })).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'integrations-mcp-tab', { fullPage: true });
});

test('user settings API/MCP tabs visual capture', async ({ page }, testInfo) => {
  test.skip(
    process.env.OPENCODE_VISUAL_VALIDATION_IDENTIFIER !== 'user-settings-api-mcp-tabs',
    'This evidence test only runs for the User settings API/MCP tabs visual identifier.',
  );

  await openUserSettings(page);

  if (IS_BASELINE_VISUAL) {
    await captureCheckpointScreenshot(page, testInfo, 'integrations-api-tab-desktop', { fullPage: true });
    await captureCheckpointScreenshot(page, testInfo, 'integrations-mcp-tab-desktop', { fullPage: true });
    await page.setViewportSize({ width: 390, height: 900 });
    await captureCheckpointScreenshot(page, testInfo, 'integrations-mcp-tab-mobile', { fullPage: true });
    return;
  }

  const integrations = page.getByTestId('integrations-settings');
  const apiTab = integrations.getByRole('tab', { name: 'API' });
  const mcpTab = integrations.getByRole('tab', { name: 'MCP' });
  const apiPanel = page.getByTestId('invoices-api-token-settings');
  const mcpPanel = page.getByTestId('mcp-connection-settings');

  await expect(apiTab).toHaveAttribute('aria-selected', 'true');
  await expect(apiPanel).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'integrations-api-tab-desktop', { fullPage: true });

  await mcpTab.click();
  await expect(mcpTab).toHaveAttribute('aria-selected', 'true');
  await expect(mcpPanel).toBeVisible();
  await expect(mcpPanel.getByLabel('MCP endpoint URL')).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'integrations-mcp-tab-desktop', { fullPage: true });

  await openUserSettings(page, { width: 390, height: 900 });
  const mobileIntegrations = page.getByTestId('integrations-settings');
  const mobileMcpTab = mobileIntegrations.getByRole('tab', { name: 'MCP' });
  const mobileMcpPanel = page.getByTestId('mcp-connection-settings');

  await mobileMcpTab.click();
  await expect(mobileMcpPanel).toBeVisible();
  await expect(mobileMcpPanel.getByLabel('MCP endpoint URL')).toBeVisible();
  await captureCheckpointScreenshot(page, testInfo, 'integrations-mcp-tab-mobile', { fullPage: true });
});
