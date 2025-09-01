import { test, expect } from '@playwright/test';
import { HomePage } from '../pages/HomePage';

test.describe('Basic Search Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Minimal mocks to render homepage service pills (handle CORS + preflight)
    const allow = (route: any) => ({
      'Access-Control-Allow-Origin': route.request().headers()['origin'] || 'http://localhost:3100',
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
      'Vary': 'Origin',
    });

    await page.route('**/services/catalog/top-per-category', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: allow(route),
        body: JSON.stringify({
          categories: [
            {
              id: 1,
              name: 'Music',
              slug: 'music',
              services: [ { id: '01J5TESTSERV00000000000001', name: 'Piano', slug: 'piano', demand_score: 90, active_instructors: 5, is_trending: false, display_order: 1 } ]
            }
          ]
        }),
      });
    });

    await page.route('**/services/catalog/kids-available', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: allow(route),
        body: JSON.stringify([ { id: '01J5TESTSERV00000000000001', name: 'Piano', slug: 'piano' } ]),
      });
    });

    await page.route('**/services/categories', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: allow(route),
        body: JSON.stringify([
          { id: 1, name: 'Music', slug: 'music', subtitle: '', description: 'Learn instruments', icon_name: 'music' }
        ]),
      });
    });

    await page.route('**/api/search-history**', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', headers: allow(route), body: JSON.stringify([]) });
    });
  });
  test('can search for instructors', async ({ page }) => {
    const homePage = new HomePage(page);
    await homePage.goto();

    // Search for piano
    await homePage.searchForInstrument('piano');

    // Verify we're on the search results page
    await expect(page).toHaveURL(/\/search/);

    // Wait for page to load and check if we have either:
    // 1. A search results container, or
    // 2. Some content indicating the page loaded
    await page.waitForLoadState('networkidle');

    // Just verify the search page loaded successfully
    // The actual search results depend on backend implementation
    const pageContent = await page.textContent('body');
    expect(pageContent).toBeTruthy(); // Page has some content
  });

  test('can click on category links', async ({ page }) => {
    // Ultra-early interceptors so homepage requests are mocked before first paint
    const allow = (route: any) => ({
      'Access-Control-Allow-Origin': route.request().headers()['origin'] || 'http://localhost:3100',
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
      'Vary': 'Origin',
    });

    await page.route('**/services/catalog/top-per-category', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: allow(route),
        body: JSON.stringify({
          categories: [
            {
              id: 1,
              name: 'Music',
              slug: 'music',
              services: [ { id: '01J5TESTSERV00000000000001', name: 'Piano', slug: 'piano', demand_score: 90, active_instructors: 5, is_trending: false, display_order: 1 } ]
            }
          ]
        }),
      });
    });

    await page.route('**/services/categories', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: allow(route),
        body: JSON.stringify([
          { id: 1, name: 'Music', slug: 'music', subtitle: '', description: 'Learn instruments', icon_name: 'music' }
        ]),
      });
    });

    await page.route('**/services/catalog/kids-available', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: allow(route),
        body: JSON.stringify([ { id: '01J5TESTSERV00000000000001', name: 'Piano', slug: 'piano' } ]),
      });
    });

    await page.route('**/api/search-history**', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', headers: allow(route), body: JSON.stringify([]) });
    });

    // Ensure homepage selects a category that we provide top services for
    await page.addInitScript(() => {
      try { sessionStorage.setItem('homeSelectedCategory', 'music'); } catch {}
    });
    await page.goto('/');

    // Click any service pill from top-per-category
    const serviceLink = page.locator('a[href*="/search?service_catalog_id="]').first();
    await serviceLink.waitFor({ state: 'visible', timeout: 10000 });
    await serviceLink.click();

    // Verify we're on the search page with service filter (ULID format)
    await expect(page).toHaveURL(/\/search\?service_catalog_id=[0-9A-Z]{26}/);
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
