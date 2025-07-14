import { test, expect } from '@playwright/test';
import { HomePage } from '../pages/HomePage';

test.describe('Basic Search Flow', () => {
  test('can search for instructors', async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.goto();

    // Search for piano
    await homePage.searchForInstrument('piano');

    // Verify we're on the search results page
    await expect(page).toHaveURL(/\/search/);

    // Wait for search results to load (either results or no results message)
    await page.waitForSelector('text=/instructor|no.*found/i', { timeout: 10000 });
  });

  test('can click on category links', async ({ page }) => {
    await page.goto('/');

    // Click on Music category
    const musicCategory = page.getByRole('link', { name: /Music/i });
    await musicCategory.click();

    // Verify we're on the search page with category filter
    await expect(page).toHaveURL(/\/search\?category=music/);
  });

  test('shows available instructors section', async ({ page }) => {
    await page.goto('/');

    // Check for "Available Right Now" section
    const availableSection = page.getByRole('heading', { name: /Available Right Now/i });
    await expect(availableSection).toBeVisible();

    // Check for at least one instructor card
    const bookNowButtons = page.getByRole('button', { name: /Book Now/i });
    const count = await bookNowButtons.count();
    expect(count).toBeGreaterThan(0);
  });

  test('shows trending section', async ({ page }) => {
    await page.goto('/');

    // Check for "Trending This Week" section
    const trendingSection = page.getByRole('heading', { name: /Trending This Week/i });
    await expect(trendingSection).toBeVisible();

    // Check for trending items
    const spanishLessons = page.getByText(/Spanish Lessons/i);
    await expect(spanishLessons).toBeVisible();
  });
});
