import { test, expect } from '@playwright/test';
import { isAnon } from '../utils/projects';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isAnon(workerInfo), `Anon-only spec (current project: ${workerInfo.project.name})`);
});

test.describe('Smoke Tests', () => {
  test('homepage loads successfully', async ({ page }) => {
    await page.goto('/');

    // Check for the main heading
    const heading = page.getByRole('heading', { name: /Instant Learning with iNSTAiNSTRU/i });
    await expect(heading).toBeVisible();

    // Check for search input
    const searchInput = page.getByPlaceholder(/Ready to learn something new/i);
    await expect(searchInput).toBeVisible();
  });

  test('navigation links are visible', async ({ page }) => {
    await page.goto('/');

    // Check for the combined login/signup link
    const authLink = page.getByRole('link', { name: /Sign up \/ Log in/i });
    await expect(authLink).toBeVisible();

    // Check for become instructor link
    const instructorLink = page.getByRole('link', { name: /Become an Instructor/i });
    await expect(instructorLink).toBeVisible();
  });

  test('can navigate to login page', async ({ page }) => {
    await page.goto('/');

    const authLink = page.getByRole('link', { name: /Sign up \/ Log in/i });
    await authLink.click();

    // Verify we're on the login page
    await expect(page).toHaveURL(/\/login/);

    // Verify login page elements - look for the brand name heading or email input
    const brandHeading = page.getByRole('heading', { name: /iNSTAiNSTRU/i });
    await expect(brandHeading).toBeVisible();

    // Also verify the email input is present
    const emailInput = page.getByPlaceholder('you@example.com');
    await expect(emailInput).toBeVisible();
  });

  test('can navigate to signup page from login', async ({ page }) => {
    await page.goto('/login');

    // Find the signup link on the login page
    const signupLink = page.getByRole('link', { name: /Sign up/i });
    await signupLink.click();

    // Verify we're on the signup page
    await expect(page).toHaveURL(/\/signup/);
  });
});

test.describe('Rate limit guardrails', () => {
  test('search shows friendly message when 429 with Retry-After', async ({ page, context }) => {
    // Ensure guest session succeeds to avoid auth redirects in CI
    await context.route(/.*\/api(?:\/proxy)?(?:\/api)?\/public\/session\/guest.*/, async (route) => {
      const origin = route.request().headers()['origin'] || 'http://localhost:3100';
      await route.fulfill({
        status: 200,
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', Vary: 'Origin' },
        contentType: 'application/json',
        body: JSON.stringify({ ok: true })
      });
    });
    // auth/me returns 401 to keep guest flow
    await context.route(/.*\/auth\/me.*/, async (route) => {
      const origin = route.request().headers()['origin'] || 'http://localhost:3100';
      await route.fulfill({
        status: 401,
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', Vary: 'Origin' },
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' })
      });
    });
    // Match direct and proxied API paths, including v1 and optional extra /api after /api/proxy
    await context.route(/.*\/api(?:\/proxy)?(?:\/api)?(?:\/v1)?\/search\/instructors.*/, async (route) => {
      const req = route.request();
      const method = req.method();
      const origin = req.headers()['origin'] || 'http://localhost:3100';
      const baseHeaders = {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        Vary: 'Origin'
      } as Record<string, string>;
      if (method === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: baseHeaders });
        return;
      }
      await route.fulfill({
        status: 429,
        headers: { ...baseHeaders, 'Content-Type': 'application/json', 'Retry-After': '5', 'Access-Control-Expose-Headers': 'Retry-After' },
        body: JSON.stringify({ detail: 'Too many requests' })
      });
    });

    await page.goto('/search?q=piano');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    // Prefer explicit test id to avoid copy variations
    await expect(page.locator('[data-testid="rate-limit-banner"]')).toBeVisible({ timeout: 30000 });
  });

  test('search shows generic friendly message when 429 without Retry-After', async ({ page, context }) => {
    // Ensure guest session succeeds to avoid auth redirects in CI
    await context.route(/.*\/api(?:\/proxy)?(?:\/api)?\/public\/session\/guest.*/, async (route) => {
      const origin = route.request().headers()['origin'] || 'http://localhost:3100';
      await route.fulfill({
        status: 200,
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', Vary: 'Origin' },
        contentType: 'application/json',
        body: JSON.stringify({ ok: true })
      });
    });
    // auth/me returns 401 to keep guest flow
    await context.route(/.*\/auth\/me.*/, async (route) => {
      const origin = route.request().headers()['origin'] || 'http://localhost:3100';
      await route.fulfill({
        status: 401,
        headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true', Vary: 'Origin' },
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Not authenticated' })
      });
    });
    // Match direct and proxied API paths, including v1 and optional extra /api after /api/proxy
    await context.route(/.*\/api(?:\/proxy)?(?:\/api)?(?:\/v1)?\/search\/instructors.*/, async (route) => {
      const req = route.request();
      const method = req.method();
      const origin = req.headers()['origin'] || 'http://localhost:3100';
      const baseHeaders = {
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
        'Access-Control-Allow-Headers': 'Content-Type, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, Authorization',
        'Access-Control-Allow-Methods': 'GET, OPTIONS',
        Vary: 'Origin'
      } as Record<string, string>;
      if (method === 'OPTIONS') {
        await route.fulfill({ status: 204, headers: baseHeaders });
        return;
      }
      await route.fulfill({
        status: 429,
        headers: { ...baseHeaders, 'Content-Type': 'application/json' },
        body: JSON.stringify({ detail: 'Too many requests' })
      });
    });

    await page.goto('/search?q=guitar');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    await expect(page.locator('[data-testid="rate-limit-banner"]')).toBeVisible({ timeout: 30000 });
  });
});
