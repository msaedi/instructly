import { expect, test, type Page, type Route } from '@playwright/test';

const instructorUser = {
  id: 'inst-user-1',
  email: 'sarah.chen@example.com',
  first_name: 'Sarah',
  last_name: 'Chen',
  roles: ['instructor'],
  permissions: [],
};

const respondJson = (route: Route, body: unknown) =>
  route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });

async function mockDashboardApis(page: Page) {
  await page.route('**/auth/me', async (route) => {
    await respondJson(route, instructorUser);
  });

  await page.route('**/instructors/me', async (route) => {
    await respondJson(route, {
      id: 'instr-profile-1',
      user_id: instructorUser.id,
      bio: 'Experienced instructor',
      service_area_boroughs: ['Manhattan'],
      preferred_teaching_locations: [],
      preferred_public_spaces: [],
      years_experience: 5,
      user: {
        first_name: 'Sarah',
        last_initial: 'C',
        has_profile_picture: false,
      },
      services: [
        {
          id: 'service-1',
          service_catalog_id: 'svc-1',
          service_catalog_name: 'Piano',
          name: 'Piano',
          description: 'Piano lessons',
          hourly_rate: 90,
          duration_options: [60],
          location_types: ['remote'],
        },
      ],
      favorited_count: 0,
    });
  });

  await page.route('**/api/addresses/service-areas/me', async (route) => {
    await respondJson(route, { items: [] });
  });

  await page.route('**/api/payments/connect/status', async (route) => {
    await respondJson(route, {
      charges_enabled: true,
      payouts_enabled: true,
      details_submitted: true,
    });
  });

  await page.route('**/api/messages/unread-count', async (route) => {
    await respondJson(route, { unread_count: 0, user_id: instructorUser.id });
  });

  await page.route('**/bookings/**', async (route) => {
    const url = new URL(route.request().url());
    const params = url.searchParams;
    if (params.get('status') === 'COMPLETED') {
      await respondJson(route, { items: [], total: 0, page: 1, per_page: 1, has_next: false, has_prev: false });
      return;
    }
    if (params.get('upcoming') === 'true') {
      await respondJson(route, { items: [], total: 0, page: 1, per_page: 100, has_next: false, has_prev: false });
      return;
    }
    await respondJson(route, { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false });
  });

  await page.route('**/api/public/instructors/**/availability**', async (route) => {
    await respondJson(route, {
      instructor_id: instructorUser.id,
      instructor_first_name: 'Sarah',
      instructor_last_initial: 'C',
      availability_by_date: {},
      timezone: 'America/New_York',
      total_available_slots: 0,
      earliest_available_date: '2025-01-01',
    });
  });

  await page.route('**/api/reviews/instructor/*/ratings', async (route) => {
    await respondJson(route, {
      overall: { rating: 4.53, total_reviews: 3, display_rating: '4.5' },
      by_service: [],
      confidence_level: 'trusted',
    });
  });
}

test.describe('[instructor] dashboard reviews snapshot', () => {
  test('renders average rating and count', async ({ page }) => {
    await mockDashboardApis(page);
    const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';

    await page.goto(`${baseURL}/instructor/dashboard`);

    await expect(page.getByTestId('reviews-avg')).toHaveText('4.5 ★');
    await expect(page.getByTestId('reviews-count')).toHaveText('3 reviews');
  });
});
