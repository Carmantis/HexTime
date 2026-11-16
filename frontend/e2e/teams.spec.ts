import { expect, test } from '@playwright/test';

import { go, signIn, useEnglish } from './helpers';

test('an invited person is asked, and joins by saying yes', async ({ page }) => {
  // The demo data has Olli invited to Verkkotiimi, not yet answered.
  await signIn(page, 'olli@example.org');
  await useEnglish(page);

  const question = page.getByRole('dialog', { name: 'Team invitation' });
  await expect(question).toContainText('Do you want to join the team Verkkotiimi?');
  await question.getByRole('button', { name: 'Join' }).click();
  await expect(question).toBeHidden();

  await go(page, 'Teams');
  await expect(page.getByRole('navigation', { name: 'Teams' })).toContainText('Verkkotiimi');
});

test('a lead invites someone from the organisation and can take it back', async ({ page }) => {
  await signIn(page, 'liisa@example.org');
  await useEnglish(page);
  await go(page, 'Teams');

  await page.getByLabel('Invite a person').fill('anna');
  await page
    .locator('.found li', { hasText: 'Anna Admin' })
    .getByRole('button', { name: 'Invite' })
    .click();
  await expect(page.getByRole('status')).toContainText('Anna Admin was invited');
  await expect(page.locator('.invitations')).toContainText('Anna Admin');

  await page.getByRole('button', { name: 'Cancel invitation: Anna Admin' }).click();
  await expect(page.locator('.invitations')).toHaveCount(0);
});
