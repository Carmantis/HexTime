import { expect, test } from '@playwright/test';

import { signIn, useEnglish } from './helpers';

test('an entry is added by hand and edited afterwards', async ({ page }) => {
  // Liisa, so the hour before now is free (the timer test is Mikko's).
  await signIn(page, 'liisa@example.org');
  await useEnglish(page);

  await page.getByRole('main').getByRole('button', { name: 'New entry' }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Description').fill('E2E manual');
  await dialog.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByRole('main').getByText('E2E manual')).toBeVisible();

  await page.getByRole('main').getByText('E2E manual').click();
  await dialog.getByLabel('Description').fill('E2E edited');
  await dialog.getByRole('button', { name: 'Save' }).click();

  await expect(page.getByRole('main').getByText('E2E edited')).toBeVisible();
  await expect(page.getByRole('main').getByText('E2E manual')).toHaveCount(0);
});

test('times are typed on the 24-hour clock, also in English', async ({ page }) => {
  // Anna has no entries in the demo data, so the morning is free.
  await signIn(page, 'anna@example.org');
  await useEnglish(page);

  await page.getByRole('main').getByRole('button', { name: 'New entry' }).first().click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Description').fill('E2E clock');
  await dialog.getByLabel('Starts').fill('25');
  await dialog.getByRole('button', { name: 'Save' }).click();
  // Not a time: the form is not sent.
  await expect(dialog).toBeVisible();

  await dialog.getByLabel('Starts').fill('730');
  await dialog.getByLabel('Ends').fill('8.15');
  await dialog.getByRole('button', { name: 'Save' }).click();

  await expect(page.getByRole('main').getByText('07:30–08:15')).toBeVisible();
});
