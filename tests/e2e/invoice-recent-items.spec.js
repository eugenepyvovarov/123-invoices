const { test, expect } = require('@playwright/test');

const { captureCheckpointScreenshot } = require('./helpers/demo-evidence');
const { loginToDashboard } = require('./helpers/auth');

async function ensureRecentItemsExpanded(component) {
  const toggle = component.locator('[data-recent-items-toggle]');
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') {
    await toggle.click();
  }
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(component.locator('[data-recent-items-wrapper]')).toBeVisible();
}

async function collapseRecentItems(component) {
  const toggle = component.locator('[data-recent-items-toggle]');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(component.locator('[data-recent-items-wrapper]')).toBeHidden();
}

async function addFirstRecentItem(component, form) {
  const recentRow = component.locator('tbody tr').first();
  await expect(recentRow).toBeVisible();
  const description = (await recentRow.locator('td').first().innerText()).trim();

  await recentRow.getByRole('button', { name: 'Add' }).click();
  await expect
    .poll(async () => {
      const values = await form
        .locator('input[name$="-description"]')
        .evaluateAll((inputs) => inputs.map((input) => input.value));
      return values.includes(description);
    })
    .toBe(true);
  return description;
}

async function fillUnsavedInputs(form, notesValue, lineValue) {
  await form.getByLabel('Notes').fill(notesValue);
  const firstDescription = form.locator('input[name$="-description"]').first();
  await firstDescription.fill(lineValue);
  await expect(form.getByLabel('Notes')).toHaveValue(notesValue);
  await expect(firstDescription).toHaveValue(lineValue);
}

async function expectUnsavedInputsPreserved(form, notesValue, lineValue) {
  await expect(form.getByLabel('Notes')).toHaveValue(notesValue);
  await expect(form.locator('input[name$="-description"]').first()).toHaveValue(lineValue);
}

test('invoice create recent tasks can be toggled without losing unsaved form input', async ({ page }, testInfo) => {
  const unsavedNotes = `Unsaved create notes for recent tasks ${testInfo.retry}`;
  const unsavedLine = `Unsaved create order-line text ${testInfo.retry}`;

  await loginToDashboard(page);

  await page.goto('/projects/');
  await expect(page.getByRole('heading', { name: 'Projects' })).toBeVisible();
  await page.getByRole('link', { name: 'Smoke Website Retainer' }).click();
  await page.getByRole('link', { name: 'New invoice' }).click();

  await expect(page.getByRole('heading', { name: 'Invoice details' })).toBeVisible();

  const form = page.locator('form[data-order-lines-formset="orderline"]').first();
  const recentItems = form.locator('[data-recent-items-component]');
  await ensureRecentItemsExpanded(recentItems);
  await expect(recentItems.locator('tbody tr').first()).toBeVisible();

  await captureCheckpointScreenshot(page, testInfo, 'invoice-create-recent-tasks-expanded');
  await captureCheckpointScreenshot(page, testInfo, 'invoice-create-recent-tasks-full-page', { fullPage: true });

  await fillUnsavedInputs(form, unsavedNotes, unsavedLine);
  await collapseRecentItems(recentItems);
  await expectUnsavedInputsPreserved(form, unsavedNotes, unsavedLine);
  await captureCheckpointScreenshot(page, testInfo, 'invoice-create-recent-tasks-collapsed');

  await ensureRecentItemsExpanded(recentItems);
  await expectUnsavedInputsPreserved(form, unsavedNotes, unsavedLine);
  await addFirstRecentItem(recentItems, form);
  await expectUnsavedInputsPreserved(form, unsavedNotes, unsavedLine);

  await captureCheckpointScreenshot(page, testInfo, 'invoice-create-recent-task-added');
});

test('draft invoice edit recent tasks can be toggled without losing unsaved form input', async ({ page }, testInfo) => {
  const unsavedNotes = `Unsaved draft-edit notes for recent tasks ${testInfo.retry}`;
  const unsavedLine = `Unsaved draft-edit order-line text ${testInfo.retry}`;

  await loginToDashboard(page);

  await page.goto('/invoices/?status=draft&date_range=all');
  await expect(page.getByRole('heading', { name: 'Invoices' })).toBeVisible();
  const draftRow = page.locator('.data-table tbody tr').filter({ hasText: 'Smoke Website Retainer' }).first();
  await expect(draftRow).toBeVisible();
  await draftRow.locator('a.link-primary').first().click();

  await expect(page.locator('h1', { hasText: /^Invoice / })).toBeVisible();
  await page.locator('[data-tab-group] a[href="#edit"]').click();
  await expect(page).toHaveURL(/\/invoices\/\d+\/\?tab=edit$/);

  const form = page.locator('#edit form[data-order-lines-formset="orderline"]');
  const recentItems = form.locator('[data-recent-items-component]');
  await ensureRecentItemsExpanded(recentItems);
  await expect(recentItems.locator('tbody tr').first()).toBeVisible();

  await captureCheckpointScreenshot(page, testInfo, 'draft-invoice-edit-recent-tasks-expanded');
  await captureCheckpointScreenshot(page, testInfo, 'draft-invoice-edit-recent-tasks-full-page', { fullPage: true });

  await fillUnsavedInputs(form, unsavedNotes, unsavedLine);
  await collapseRecentItems(recentItems);
  await expectUnsavedInputsPreserved(form, unsavedNotes, unsavedLine);
  await captureCheckpointScreenshot(page, testInfo, 'draft-invoice-edit-recent-tasks-collapsed');
  await captureCheckpointScreenshot(page, testInfo, 'draft-invoice-edit-recent-tasks-collapsed-full-page', { fullPage: true });

  await ensureRecentItemsExpanded(recentItems);
  await expectUnsavedInputsPreserved(form, unsavedNotes, unsavedLine);
  await addFirstRecentItem(recentItems, form);
  await expectUnsavedInputsPreserved(form, unsavedNotes, unsavedLine);

  await captureCheckpointScreenshot(page, testInfo, 'draft-invoice-edit-recent-task-added');
});
