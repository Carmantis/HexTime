import { expect, test } from '@playwright/test';

import { PASSWORD, signIn } from './helpers';

test('a wrong password is refused without saying which part was wrong', async ({ page }) => {
  await page.goto('/#/login');
  await page.getByLabel('Email').fill('mikko@example.org');
  await page.getByLabel('Password', { exact: true }).fill(`${PASSWORD}-wrong`);
  await page.getByRole('button', { name: 'Sign in' }).click();

  await expect(page.getByRole('alert')).toHaveText('Wrong email or password.');
});

test('signing in and out', async ({ page }) => {
  await signIn(page, 'mikko@example.org');
  await expect(page.getByText('Mikko Member')).toBeVisible();

  await page.getByRole('button', { name: /sign out|kirjaudu ulos/i }).click();

  // The sign-in page, in whichever language Mikko last used.
  await expect(page).toHaveURL(/#\/login/);
  await expect(page.locator('input[type=email]')).toBeVisible();
});
