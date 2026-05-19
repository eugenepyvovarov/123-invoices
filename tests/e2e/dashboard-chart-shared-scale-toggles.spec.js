const { test, expect } = require('@playwright/test');

const { ensureActiveCompany, loginToDashboard } = require('./helpers/auth');
const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');

async function getAxisLabels(chart) {
  return chart.locator('.dashboard-chart__y-axis-label').allTextContents();
}

async function getMonthMetrics(chart) {
  return chart.locator('.dashboard-chart__bar').evaluateAll((bars) => bars.map((bar, index) => {
    const row = bar.closest('tr');
    const monthLabel = row?.querySelector('.dashboard-chart__month-label')?.textContent?.trim() || `month-${index}`;
    const revenueBar = row?.querySelector('.dashboard-chart__bar-revenue');
    const expenseBar = row?.querySelector('.dashboard-chart__bar-expense');
    const revenueRect = revenueBar?.getBoundingClientRect();
    const expenseRect = expenseBar?.getBoundingClientRect();

    return {
      monthLabel,
      revenueHeight: revenueRect ? Number(revenueRect.height.toFixed(2)) : 0,
      expenseHeight: expenseRect ? Number(expenseRect.height.toFixed(2)) : 0,
      revenueLeft: revenueRect ? Number(revenueRect.left.toFixed(2)) : 0,
      revenueRight: revenueRect ? Number(revenueRect.right.toFixed(2)) : 0,
      expenseLeft: expenseRect ? Number(expenseRect.left.toFixed(2)) : 0,
      expenseRight: expenseRect ? Number(expenseRect.right.toFixed(2)) : 0,
    };
  }));
}

async function findCompanyWithExpenseHigherThanRevenue(page, chart) {
  const activeCompanyName = page.getByTestId('company-switcher-active-name');
  const companyNames = await page.getByTestId('company-switcher-option').evaluateAll((options) => {
    const names = options
      .map((option) => option.textContent?.trim())
      .filter(Boolean);

    return [...new Set(names)];
  });

  const namesToCheck = [
    ((await activeCompanyName.textContent()) || '').trim(),
    ...companyNames,
  ].filter(Boolean);

  const checkedNames = [];

  for (const companyName of [...new Set(namesToCheck)]) {
    await ensureActiveCompany(page, companyName);
    await expect(activeCompanyName).toHaveText(companyName);
    await expect(chart).toBeVisible();

    const monthMetrics = await getMonthMetrics(chart);
    const monthWithExpenseAboveRevenue = monthMetrics.find((month) => month.expenseHeight > month.revenueHeight);

    if (monthWithExpenseAboveRevenue) {
      return { companyName, monthWithExpenseAboveRevenue, monthMetrics };
    }

    checkedNames.push(companyName);
  }

  throw new Error(
    `Could not find a company with a month where expense height exceeds revenue height. Checked: ${checkedNames.join(', ')}`,
  );
}

test('dashboard chart shared scale toggles preserve stable axis semantics', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1600, height: 1200 });
  await loginToDashboard(page);

  const chart = page.locator('[data-dashboard-chart]');
  const revenueToggle = chart.getByRole('button', { name: 'Revenue' });
  const expenseToggle = chart.getByRole('button', { name: 'Expenses' });

  await expect(chart).toBeVisible();

  const { companyName, monthWithExpenseAboveRevenue } = await findCompanyWithExpenseHigherThanRevenue(page, chart);
  const axisLabelsBeforeToggles = await getAxisLabels(chart);
  const guideLineCount = await chart.locator('.dashboard-chart__guide-line').count();
  const monthCount = await chart.locator('.dashboard-chart__bar').count();

  await expect(page.getByTestId('company-switcher-active-name')).toHaveText(companyName);
  await expect(chart.getByRole('heading', { name: 'Revenue vs Expense' })).toBeVisible();
  await expect(chart.locator('.dashboard-chart__guide-line')).toHaveCount(guideLineCount);
  await expect(chart.locator('.dashboard-chart__y-axis-label')).toHaveCount(axisLabelsBeforeToggles.length);
  await expect(chart.locator('.dashboard-chart__x-axis-label')).toHaveCount(monthCount);
  await expect(revenueToggle).toHaveAttribute('aria-pressed', 'true');
  await expect(expenseToggle).toHaveAttribute('aria-pressed', 'true');

  await captureCheckpointScreenshot(chart, testInfo, 'chart-default-state-with-axes-and-toggles');

  expect(monthWithExpenseAboveRevenue.expenseHeight).toBeGreaterThan(monthWithExpenseAboveRevenue.revenueHeight);
  expect(monthWithExpenseAboveRevenue.expenseLeft).toBeGreaterThan(monthWithExpenseAboveRevenue.revenueLeft);
  expect(monthWithExpenseAboveRevenue.revenueRight).toBeLessThan(monthWithExpenseAboveRevenue.expenseLeft);

  await captureCheckpointScreenshot(chart, testInfo, 'chart-expense-exceeds-revenue');

  await expenseToggle.click();

  await expect(expenseToggle).toHaveAttribute('aria-pressed', 'false');
  await expect(expenseToggle).toHaveAttribute('aria-disabled', 'false');
  await expect(chart.locator('[data-dashboard-chart-series="expense"][hidden]')).toHaveCount(monthCount);
  await expect(chart.locator('[data-dashboard-chart-series="revenue"]:not([hidden])')).toHaveCount(monthCount);
  await expect.soft(await getAxisLabels(chart)).toEqual(axisLabelsBeforeToggles);
  await expect(chart.locator('.dashboard-chart__guide-line')).toHaveCount(guideLineCount);

  await captureCheckpointScreenshot(chart, testInfo, 'chart-expenses-hidden-stable-scale');

  await expenseToggle.click();

  await expect(expenseToggle).toHaveAttribute('aria-pressed', 'true');
  await expect(chart.locator('[data-dashboard-chart-series="expense"][hidden]')).toHaveCount(0);

  await revenueToggle.click();

  await expect(revenueToggle).toHaveAttribute('aria-pressed', 'false');
  await expect(chart.locator('[data-dashboard-chart-series="revenue"][hidden]')).toHaveCount(monthCount);
  await expect(chart.locator('[data-dashboard-chart-series="expense"]:not([hidden])')).toHaveCount(monthCount);
  await expect(expenseToggle).toHaveAttribute('aria-disabled', 'true');
  await expect(expenseToggle).toHaveAttribute('data-dashboard-chart-toggle-locked', 'true');
  await expect.soft(await getAxisLabels(chart)).toEqual(axisLabelsBeforeToggles);
  await expect(chart.locator('.dashboard-chart__guide-line')).toHaveCount(guideLineCount);

  await captureCheckpointScreenshot(chart, testInfo, 'chart-revenue-hidden-stable-scale');
  await expect(expenseToggle).toHaveAttribute('aria-pressed', 'true');
  await expect(chart.locator('[data-dashboard-chart-series="expense"]:not([hidden])')).toHaveCount(monthCount);
  await expect(revenueToggle).toHaveAttribute('aria-pressed', 'false');
  await expect(revenueToggle).toHaveAttribute('aria-disabled', 'false');
});
