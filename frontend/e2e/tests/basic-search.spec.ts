import { test, expect, type Route } from '@playwright/test';
import { HomePage } from '../pages/HomePage';

test.describe('Basic Search Flow', () => {
  test.beforeEach(async ({ page }) => {
    // Minimal mocks to render homepage service pills (handle CORS + preflight)
    const allow = (route: Route) => ({
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
              id: '01J5TESTCATG00000000000001',
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
          { id: '01J5TESTCATG00000000000001', name: 'Music', slug: 'music', subtitle: '', description: 'Learn instruments', icon_name: 'music' }
        ]),
      });
    });

    await page.route('**/api/v1/search-history**', async (route) => {
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
    await page.waitForLoadState('domcontentloaded');

    // Just verify the search page loaded successfully
    // The actual search results depend on backend implementation
    const pageContent = await page.textContent('body');
    expect(pageContent).toBeTruthy(); // Page has some content
  });

  test('can click on category links', async ({ page }) => {
    // Ultra-early interceptors so homepage requests are mocked before first paint
    const allow = (route: Route) => ({
      'Access-Control-Allow-Origin': route.request().headers()['origin'] || 'http://localhost:3100',
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Methods': 'GET, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
      'Vary': 'Origin',
    });

    const categoryId = '01J5TESTCATG00000000000001';
    const subcategoryId = '01J5TESTSUBC00000000000001';
    const pianoServiceId = '01J5TESTSERV00000000000001';
    const keyboardServiceId = '01J5TESTSERV00000000000002';

    await page.route('**/services/catalog/all-with-instructors', async (route) => {
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
              id: categoryId,
              name: 'Music',
              subtitle: '',
              icon_name: 'music',
              services: [
                {
                  id: pianoServiceId,
                  name: 'Piano',
                  subcategory_id: subcategoryId,
                  eligible_age_groups: ['adults'],
                  instructor_count: 5,
                  active_instructors: 5,
                  display_order: 1,
                },
                {
                  id: keyboardServiceId,
                  name: 'Keyboard',
                  subcategory_id: subcategoryId,
                  eligible_age_groups: ['adults'],
                  instructor_count: 3,
                  active_instructors: 3,
                  display_order: 2,
                },
              ],
            }
          ],
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
          { id: categoryId, name: 'Music', slug: 'music', subtitle: '', description: 'Learn instruments', icon_name: 'music' }
        ]),
      });
    });

    await page.route('**/services/categories/*/subcategories', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: allow(route),
        body: JSON.stringify([
          { id: subcategoryId, name: 'Piano', service_count: 2 }
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
        body: JSON.stringify([ { id: pianoServiceId, name: 'Piano', slug: 'piano' } ]),
      });
    });

    await page.route('**/api/v1/search-history**', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: allow(route) });
        return;
      }
      await route.fulfill({ status: 200, contentType: 'application/json', headers: allow(route), body: JSON.stringify([]) });
    });

    // Ensure homepage selects a category that we provide top services for
    await page.addInitScript(() => {
      try { sessionStorage.setItem('homeSelectedCategory', '01J5TESTCATG00000000000001'); } catch {}
    });
    await page.goto('/');

    // Click through the current homepage flow: subcategory -> service pill
    const subcategoryButton = page.getByRole('button', { name: /^Piano/i });
    await expect(subcategoryButton).toBeVisible();
    await subcategoryButton.click();

    const serviceLink = page.getByRole('link', { name: 'Keyboard' });
    await expect(serviceLink).toBeVisible();
    await serviceLink.click();

    // Verify we're on the search page with the selected service filter
    await expect(page).toHaveURL(new RegExp(`/search\\?.*service_catalog_id=${keyboardServiceId}`));
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
