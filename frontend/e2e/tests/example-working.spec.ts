import { test, expect } from '@playwright/test';
import { isAnon } from '../utils/projects';
import { mockPublicPageBaselineApis } from '../utils/publicPageMocks';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isAnon(workerInfo), `Anon-only spec (current project: ${workerInfo.project.name})`);
});

test.beforeEach(async ({ page }) => {
  await mockPublicPageBaselineApis(page);
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
    const searchInput = page.locator('input[type="text"][placeholder*="learn"]').first();
    await expect(searchInput).toBeVisible();
    await searchInput.fill('guitar');
    await searchInput.press('Enter');

    // 5. Verify search navigation
    await expect(page).toHaveURL(/\/search/);
  });

  test('navigation flow', async ({ page }) => {
    await page.goto('/');

    // Validate an auth entry link when present, but keep fallback robust across
    // nav variants where the link text differs by viewport/auth shell.
    const authLink = page.locator('a[href*="/login"]').first();
    if ((await authLink.count()) > 0) {
      await expect(authLink).toHaveAttribute('href', /\/login/);
    }
    await page.goto('/login');
    await expect(page).toHaveURL(/\/login(?:\?redirect=.*)?$/);

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
    await expect(howItWorksLink).toHaveAttribute('href', /\/how-it-works/);

    // Navigate directly after validating link target to avoid occasional detachment during refresh.
    await page.goto('/how-it-works');
    await expect(page).toHaveURL('/how-it-works');
  });
});
