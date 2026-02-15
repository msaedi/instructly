import type { Page, Route } from '@playwright/test';

type BackgroundMockOptions = {
  userId?: string;
};

type RouteRegistrar = {
  route: (url: string | RegExp, handler: (route: Route) => Promise<void>) => Promise<void>;
};

const DEFAULT_USER_ID = 'mock-user';

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

const EMPTY_PAGE = {
  items: [],
  total: 0,
  page: 1,
  per_page: 50,
  has_next: false,
  has_prev: false,
};

/**
 * Shared auth scaffolding for E2E specs that mock authenticated pages.
 *
 * Why this exists:
 * - Frontend now attempts /api/v1/auth/refresh after any 401.
 * - If refresh is not mocked in auth-mocked specs, interceptor triggers logout redirect.
 * - Some dashboard background calls (notifications/SSE/bookings) can return 401 unless mocked.
 */
export async function mockAuthenticatedPageBackgroundApis(
  page: Page | RouteRegistrar,
  options: BackgroundMockOptions = {}
) {
  const routeTarget: RouteRegistrar = page;
  const userId = options.userId ?? DEFAULT_USER_ID;

  await routeTarget.route('**/api/v1/auth/me', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, {
      id: userId,
      email: 'e2e-user@example.com',
      first_name: 'E2E',
      last_name: 'User',
      roles: ['instructor'],
      permissions: [],
      is_active: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  const instructorProfile = {
    id: `profile-${userId}`,
    user_id: userId,
    bio: 'E2E mock instructor profile',
    service_area_summary: 'Manhattan',
    service_area_boroughs: ['Manhattan'],
    service_area_neighborhoods: [],
    years_experience: 5,
    min_advance_booking_hours: 2,
    buffer_time_minutes: 0,
    preferred_teaching_locations: [],
    preferred_public_spaces: [],
    services: [],
    user: {
      id: userId,
      first_name: 'E2E',
      last_name: 'User',
      roles: ['instructor'],
    },
    is_live: true,
  };

  await routeTarget.route('**/api/v1/instructors/me', async (route) => {
    const method = route.request().method();
    if (method === 'GET' || method === 'PUT' || method === 'PATCH') {
      await fulfillJson(route, instructorProfile);
      return;
    }
    await route.fallback();
  });

  await routeTarget.route('**/instructors/me', async (route) => {
    const method = route.request().method();
    if (method === 'GET' || method === 'PUT' || method === 'PATCH') {
      await fulfillJson(route, instructorProfile);
      return;
    }
    await route.fallback();
  });

  await routeTarget.route('**/api/v1/auth/refresh', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { message: 'Session refreshed' });
  });

  await routeTarget.route('**/api/v1/public/session/guest', async (route) => {
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

  await routeTarget.route('**/api/v1/sse/token', async (route) => {
    if (route.request().method() !== 'POST') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { token: 'mock-sse-token' });
  });

  await routeTarget.route('**/api/v1/notifications/unread-count', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { unread_count: 0 });
  });

  await routeTarget.route('**/api/v1/notifications**', async (route) => {
    const method = route.request().method();
    if (method === 'GET') {
      await fulfillJson(route, { notifications: [], unread_count: 0, total: 0 });
      return;
    }
    if (method === 'POST' || method === 'DELETE') {
      await fulfillJson(route, { success: true });
      return;
    }
    await route.fallback();
  });

  await routeTarget.route('**/api/v1/messages/unread-count', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { unread_count: 0, user_id: userId });
  });

  await routeTarget.route('**/api/v1/conversations**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { conversations: [] });
  });

  await routeTarget.route('**/api/v1/instructor-bookings/upcoming**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, EMPTY_PAGE);
  });

  await routeTarget.route('**/api/v1/instructor-bookings/completed**', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, EMPTY_PAGE);
  });

  await routeTarget.route('**/api/v1/payments/connect/status', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, {
      charges_enabled: true,
      payouts_enabled: true,
      details_submitted: true,
    });
  });

  await routeTarget.route('**/api/v1/payments/earnings', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, {
      total_earned: 0,
      total_fees: 0,
      booking_count: 0,
      average_earning: 0,
    });
  });

  await routeTarget.route('**/api/v1/addresses/service-areas/me', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    await fulfillJson(route, { items: [], total: 0 });
  });

  await routeTarget.route('**/api/v1/instructor-referrals/popup-data', async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    // Default to disabled popup in non-referral specs.
    // Referral-specific specs register a later route that overrides this.
    await fulfillJson(route, { detail: 'Not found' }, 404);
  });
}
