import { expect, test } from '@playwright/test';

test('a spoken request becomes a confirmed reminder in the quest log', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByTestId('hint')).toHaveText(/Hold the button/);

  await page.getByRole('button', { name: /hold to talk/i }).hover();
  await page.mouse.down();
  await page.waitForTimeout(1500);
  await page.mouse.up();

  await expect(page.getByTestId('caption-you')).toContainText('Remind me to stretch');
  const card = page.getByTestId('pending-action');
  await expect(card).toContainText('New reminder');
  await expect(card).toContainText('a reminder to stretch, tomorrow at 9 AM');

  await card.getByRole('button', { name: 'Save' }).click();
  await expect(page.getByTestId('saved')).toContainText('Saved');
  await expect(card).toBeHidden();

  await page.getByRole('link', { name: 'Quest log', exact: true }).click();
  await expect(page.getByTestId('reminder')).toContainText('stretch');
});
