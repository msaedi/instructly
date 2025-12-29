import { test, expect, type Route } from '@playwright/test';
import { setupAllMocks, TEST_ULIDS } from '../fixtures/api-mocks';

const respondWithCors = async (route: Route, payload: unknown, status = 200) => {
  const origin = route.request().headers()['origin'] || 'http://localhost:3100';
  await route.fulfill({
    status,
    contentType: 'application/json',
    headers: {
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Credentials': 'true',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, Cache-Control, Pragma, X-Session-ID, X-Search-Origin, X-Guest-Session-ID, X-Guest-Session-Id',
      'Vary': 'Origin',
    },
    body: JSON.stringify(payload),
  });
};

test.describe('Scheduled Payment Booking (>24h)', () => {
  test.beforeEach(async ({ page, context }) => {
    await context.addCookies([
      {
        name: 'access_token',
        value: 'mock_access_token_123456',
        domain: 'localhost',
        path: '/',
      },
    ]);

    await page.route('**/api/v1/bookings**', async (route) => {
      if (route.request().method() === 'GET') {
        await respondWithCors(route, {
          items: [],
          total: 0,
          page: 1,
          page_size: 50,
          pages: 1,
        });
        return;
      }
      await route.fallback();
    });

    await setupAllMocks(page, context, { forceAuth: true });

    await page.route('**/api/v1/auth/me', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await respondWithCors(route, {}, 204);
        return;
      }
      await respondWithCors(route, {
        id: TEST_ULIDS.user1,
        email: 'john.smith@example.com',
        first_name: 'John',
        last_name: 'Smith',
        role: 'student',
        roles: ['student'],
        permissions: [],
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    });

    await page.route('**/api/v1/payments/methods', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await respondWithCors(route, {}, 204);
        return;
      }
      await respondWithCors(route, [
        {
          id: 'pm_test_card',
          last4: '4242',
          brand: 'Visa',
          is_default: true,
          created_at: new Date().toISOString(),
        },
      ]);
    });

    await page.route('**/api/v1/payments/credits', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await respondWithCors(route, {}, 204);
        return;
      }
      await respondWithCors(route, { available: 0, expires_at: null, pending: 0 });
    });

    await page.route('**/api/v1/payments/checkout', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await respondWithCors(route, {}, 204);
        return;
      }
      await respondWithCors(route, {
        success: true,
        payment_intent_id: 'pi_test_scheduled',
        status: 'scheduled',
        amount: 6720,
        application_fee: 0,
        client_secret: null,
        requires_action: false,
      });
    });

    await page.route('**/api/v1/pricing/preview', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await respondWithCors(route, {}, 204);
        return;
      }
      await respondWithCors(route, {
        base_price_cents: 6000,
        student_fee_cents: 720,
        instructor_platform_fee_cents: 0,
        credit_applied_cents: 0,
        student_pay_cents: 6720,
        application_fee_cents: 0,
        top_up_transfer_cents: 0,
        instructor_tier_pct: null,
        line_items: [],
      });
    });

    await page.route('**/api/v1/bookings/*/pricing**', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await respondWithCors(route, {}, 204);
        return;
      }
      await respondWithCors(route, {
        base_price_cents: 6000,
        student_fee_cents: 720,
        instructor_platform_fee_cents: 0,
        credit_applied_cents: 0,
        student_pay_cents: 6720,
        application_fee_cents: 0,
        top_up_transfer_cents: 0,
        instructor_tier_pct: null,
        line_items: [],
      });
    });

    await page.route('**/api/v1/config/pricing', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await respondWithCors(route, {}, 204);
        return;
      }
      await respondWithCors(route, {
        config: {
          student_fee_pct: 0.12,
          instructor_tiers: [],
          price_floor_cents: {
            private_in_person: 0,
            private_remote: 0,
          },
        },
        updated_at: new Date().toISOString(),
      });
    });
  });

  test('booking more than 24h away succeeds with scheduled status', async ({ page }) => {
    const futureDate = new Date();
    futureDate.setDate(futureDate.getDate() + 7);
    const bookingDate = futureDate.toISOString().split('T')[0];

    await page.addInitScript(
      ({ bookingData, serviceId }) => {
        sessionStorage.setItem('bookingData', JSON.stringify(bookingData));
        sessionStorage.setItem('serviceId', serviceId);
      },
      {
        bookingData: {
          bookingId: '',
          instructorId: TEST_ULIDS.instructor8,
          instructorName: 'Sarah C.',
          lessonType: 'Piano',
          date: bookingDate,
          startTime: '10:00',
          endTime: '11:00',
          duration: 60,
          location: 'Online',
          basePrice: 60,
          totalAmount: 67.2,
          bookingType: 'standard',
          paymentStatus: 'scheduled',
          metadata: { serviceId: TEST_ULIDS.service1 },
        },
        serviceId: TEST_ULIDS.service1,
      }
    );

    await page.goto('/student/booking/confirm', { waitUntil: 'domcontentloaded' });

    const bookNowButton = page.getByRole('button', { name: 'Book now!' });
    await expect(bookNowButton).toBeEnabled({ timeout: 10000 });
    await bookNowButton.click();

    await expect(
      page.getByRole('heading', { name: /booking confirmed/i })
    ).toBeVisible({ timeout: 10000 });
    await expect(page.getByText(/payment failed/i)).not.toBeVisible();
  });
});
