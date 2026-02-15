import type { Page, Route } from '@playwright/test';

type RouteRegistrar = {
  route: (url: string | RegExp, handler: (route: Route) => Promise<void>) => Promise<void>;
};

const fulfillJson = async (
  route: Route,
  body: unknown,
  status = 200,
  headers: Record<string, string> = {}
) => {
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers,
    body: JSON.stringify(body),
  });
};

/**
 * Stabilizes public-page E2E runs against auth refresh/log-out cascades.
 * These routes are intentionally generic and can be overridden by spec-specific
 * routes registered later in the same test.
 */
export async function mockPublicPageBaselineApis(page: Page | RouteRegistrar) {
  await page.route('**/api/v1/public/session/guest', async (route) => {
    const method = route.request().method();
    if (method === 'OPTIONS') {
      await route.fulfill({ status: 204 });
      return;
    }
    if (method !== 'POST') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { ok: true });
  });

  await page.route('**/api/v1/auth/refresh', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { message: 'Session refreshed' });
  });

  await page.route('**/api/v1/auth/me', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, {
      id: 'public-user',
      email: 'public-user@example.com',
      first_name: 'Public',
      last_name: 'User',
      roles: [],
      permissions: [],
      is_active: true,
    });
  });
}
