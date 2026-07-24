const { test, expect } = require('@playwright/test');

const { loginToDashboard } = require('./helpers/auth');

const IS_BASELINE_VISUAL = process.env.OPENCODE_VISUAL_VALIDATION_TARGET === 'baseline';

test.use({ storageState: { cookies: [], origins: [] } });

test.beforeEach(() => {
  test.skip(IS_BASELINE_VISUAL, 'Baseline visual-validation targets may not include the API/MCP integration tabs yet.');
});

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
