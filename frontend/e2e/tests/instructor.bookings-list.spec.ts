import { expect, test, type Route } from '@playwright/test';

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

test.describe('[instructor] bookings list', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/auth/me', async (route) => {
      await respondJson(route, instructorUser);
    });
  });

  test('shows upcoming and past bookings from API data', async ({ page }) => {
    let resolveUpcoming: (() => void) | null = null;
    let resolvePast: (() => void) | null = null;
    const upcomingRequest = new Promise<void>((resolve) => {
      resolveUpcoming = resolve;
    });
    const pastRequest = new Promise<void>((resolve) => {
      resolvePast = resolve;
    });

    // Mock v1 instructor-bookings endpoints
    await page.route('**/api/v1/instructor-bookings/**', async (route) => {
      const url = new URL(route.request().url());
      const pathname = url.pathname;

      const isUpcomingCall = pathname.endsWith('/upcoming');
      const isPastCall = pathname.endsWith('/completed');

      if (isUpcomingCall) {
        resolveUpcoming?.();
        await respondJson(route, {
          items: [
            {
              id: 'booking-upcoming-1',
              booking_date: '2025-01-10',
              start_time: '15:00:00',
              status: 'CONFIRMED',
              service_name: 'Jazz Piano',
              total_price: 95,
              student: { first_name: 'Emma', last_name: 'Johnson' },
              instructor: { full_name: 'Sarah Chen' },
            },
          ],
          total: 1,
          page: 1,
          per_page: 50,
          has_next: false,
          has_prev: false,
        });
        return;
      }

      if (isPastCall) {
        resolvePast?.();
        await respondJson(route, {
          items: [
            {
              id: 'booking-past-1',
              booking_date: '2024-12-15',
              start_time: '11:00:00',
              status: 'COMPLETED',
              service_name: 'Music Theory',
              total_price: 120,
              student: { first_name: 'Emma', last_name: 'Johnson' },
              instructor: { full_name: 'Sarah Chen' },
            },
          ],
          total: 1,
          page: 1,
          per_page: 50,
          has_next: false,
          has_prev: false,
        });
        return;
      }

      await route.continue();
    });

    const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';
    await page.goto(`${baseURL}/instructor/bookings`);

    await upcomingRequest;

    const upcomingCards = page.getByTestId('booking-card');
    await expect(upcomingCards.first()).toContainText('Emma Johnson');
    await expect(upcomingCards.first()).toContainText(/Confirmed/i);

    await page.getByRole('tab', { name: /past/i }).click();
    await pastRequest;
    const pastCards = page.getByTestId('booking-card');
    await expect(pastCards.first()).toContainText('Emma Johnson');
    await expect(pastCards.first()).toContainText(/Completed/i);
  });
});
