import { expect, test } from '@playwright/test';

import { go, signIn, useEnglish } from './helpers';

test('the period report downloads as a PDF', async ({ page }) => {
  await signIn(page, 'liisa@example.org');
  await useEnglish(page);
  await go(page, 'Reports');
  // The demo data is the last five weekdays: a year always contains them.
  await page.getByRole('tab', { name: 'Year' }).click();

  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export PDF' }).click();

  expect((await download).suggestedFilename()).toMatch(/^hextime-.*\.pdf$/);
});

test('the team report shows each member and downloads', async ({ page }) => {
  await signIn(page, 'mikko@example.org');
  await useEnglish(page);
  await go(page, 'Reports');
  await page.getByRole('tab', { name: 'Year' }).click();
  await page.getByLabel('Whose hours').selectOption({ label: 'Team: Verkkotiimi' });

  await expect(page.getByRole('heading', { name: 'Hours by member' })).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Team PDF' }).click();

  expect((await download).suggestedFilename()).toMatch(/^hextime-verkkotiimi-.*\.pdf$/);
});
