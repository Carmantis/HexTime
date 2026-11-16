import { expect, type Page } from '@playwright/test';

/** Every demo user's password (backend/scripts/dev_seed.py). */
export const PASSWORD = 'hextime-dev-123';

/** Sign in as one of the demo users and wait for the app. */
export async function signIn(page: Page, email: string): Promise<void> {
  await page.goto('/#/login');
  await page.getByLabel('Email').fill(email);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('navigation', { name: 'HexTime' })).toBeVisible();
}

/** The demo users answer in Finnish by default; the tests read English. */
export async function useEnglish(page: Page): Promise<void> {
  const response = await page.request.patch('/api/v1/me', {
    data: { locale: 'en' },
    headers: { 'X-HexTime-CSRF': '1' },
  });
  expect(response.ok()).toBeTruthy();
  await page.reload();
}

export async function go(page: Page, view: string): Promise<void> {
  await page
    .getByRole('navigation', { name: 'HexTime' })
    .getByRole('button', { name: view })
    .click();
}
