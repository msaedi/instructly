import { test, expect } from '@playwright/test';
import { isAnon } from '../utils/projects';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isAnon(workerInfo), `Anon-only spec (current project: ${workerInfo.project.name})`);
});

test.describe('Working E2E Examples', () => {
  test('complete homepage interaction flow', async ({ page }) => {
    // 1. Go to homepage
    await page.goto('/');

    // 2. Verify page loaded
    await expect(
      page.getByRole('heading', { name: /Instant Learning with iNSTAiNSTRU/i })
    ).toBeVisible();

    // 3. Verify category exists (but skip clicking since services need backend)
    const musicCategory = page.getByText('Music').first();
    await expect(musicCategory).toBeVisible();

    // 4. Try the search functionality instead
    const searchInput = page.getByPlaceholder(/Ready to learn something new/i);
    await searchInput.fill('guitar');
    await searchInput.press('Enter');

    // 5. Verify search navigation
    await expect(page).toHaveURL(/\/search/);
  });

  test('navigation flow', async ({ page }) => {
    await page.goto('/');

    // Navigate to login
    await page.getByRole('link', { name: /Sign up \/ Log in/i }).click();
    await expect(page).toHaveURL('/login');

    // Navigate to signup from login page
    await page.getByRole('link', { name: /Sign up/i }).click();
    await expect(page).toHaveURL('/signup');

    // Go back home
    await page.goto('/');
    await expect(page).toHaveURL('/');
  });

  test('footer navigation', async ({ page }) => {
    await page.goto('/');

    // Scroll to footer
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));

    // Check footer links are visible
    const howItWorksLink = page.getByRole('link', { name: /How it Works/i });
    await expect(howItWorksLink).toBeVisible();

    // Click a footer link
    await howItWorksLink.click();
    await expect(page).toHaveURL('/how-it-works');
  });
});
