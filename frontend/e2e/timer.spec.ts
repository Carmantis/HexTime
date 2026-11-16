import { expect, test } from '@playwright/test';

import { signIn, useEnglish } from './helpers';

test('the timer starts and stops, and the entry shows up today', async ({ page }) => {
  await signIn(page, 'mikko@example.org');
  await useEnglish(page);

  await page.getByPlaceholder('What are you working on?').fill('E2E timer');
  await page.getByLabel('Project').selectOption({ label: 'Asiakassivut' });
  // A team project: the timer says whose it is.
  await expect(page.getByText('Verkkotiimi', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Start' }).click();
  await expect(page.getByRole('button', { name: 'Stop' })).toBeVisible();

  // An entry must end after it starts.
  await page.waitForTimeout(1500);
  await page.getByRole('button', { name: 'Stop' }).click();

  await expect(page.getByRole('button', { name: 'Start' })).toBeVisible();
  await expect(page.getByRole('main').getByText('E2E timer')).toBeVisible();
});
