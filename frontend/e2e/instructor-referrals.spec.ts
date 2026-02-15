import { expect, test, type Page, type Route } from '@playwright/test';
import { isInstructor } from './utils/projects';
import { bypassGateIfPresent } from './utils/gate';
import { mockAuthenticatedPageBackgroundApis } from './utils/authenticatedPageMocks';

type NavShare = Navigator & {
  share?: (data?: ShareData) => Promise<void>;
  canShare?: (data?: ShareData) => boolean;
  clipboard?: Partial<Clipboard>;
};

declare global {
  interface Window {
    __shared: ShareData | null;
    __copied: string | null;
  }
}

test.use({ permissions: ['clipboard-read', 'clipboard-write'] });

test.beforeAll(({}, workerInfo) => {
  test.skip(
    !isInstructor(workerInfo),
    `Instructor-only spec (current project: ${workerInfo.project.name})`
  );
});

test.skip(Boolean(process.env.CI) && !process.env.CI_LOCAL_E2E, 'local-only smoke; opt-in via CI_LOCAL_E2E=1');

test.beforeEach(async ({ page, context }) => {
  await context.addInitScript(() => {
    window.__shared = null;
    window.__copied = null;

    const nav = navigator as NavShare;

    try {
      Object.defineProperty(nav, 'canShare', {
        configurable: true,
        value: () => true,
      });
    } catch {}

    try {
      Object.defineProperty(nav, 'share', {
        configurable: true,
        value: (data?: ShareData) => {
          window.__shared = data ?? {};
          return Promise.resolve();
        },
      });
    } catch {}

    try {
      if (!('clipboard' in nav)) {
        Object.defineProperty(nav, 'clipboard', {
          configurable: true,
          value: {
            writeText: (text: string) => {
              window.__copied = text;
              return Promise.resolve();
            },
            readText: () => Promise.resolve(''),
          },
        });
      } else if (nav.clipboard) {
        Object.defineProperty(nav.clipboard, 'writeText', {
          configurable: true,
          value: (text: string) => {
            window.__copied = text;
            return Promise.resolve();
          },
        });

        if (!nav.clipboard.readText) {
          Object.defineProperty(nav.clipboard, 'readText', {
            configurable: true,
            value: () => Promise.resolve(''),
          });
        }
      }
    } catch {}

    localStorage.setItem('instructor_referral_popup_dismissed', 'true');
  });

  // Register baseline auth-related background mocks first.
  // Spec-specific route stubs below intentionally override these when needed.
  await mockAuthenticatedPageBackgroundApis(page, { userId: instructorUser.id });
  await mockDashboardApis(page);
});

const DEFAULT_BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';

const instructorUser = {
  id: 'inst-user-1',
  email: 'sarah.chen@example.com',
  first_name: 'Sarah',
  last_name: 'Chen',
  roles: ['instructor'],
  permissions: [],
};

const defaultStats = {
  referral_code: 'TESTCODE',
  referral_link: 'https://instainstru.com/r/TESTCODE',
  total_referred: 2,
  pending_payouts: 1,
  completed_payouts: 1,
  total_earned_cents: 7500,
  is_founding_phase: true,
  founding_spots_remaining: 42,
  current_bonus_cents: 7500,
};

const defaultPopupData = {
  is_founding_phase: true,
  bonus_amount_cents: 7500,
  founding_spots_remaining: 42,
  referral_code: 'TESTCODE',
  referral_link: 'https://instainstru.com/r/TESTCODE',
};

const respondJson = async (route: Route, body: unknown, status = 200) => {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
};

async function mockDashboardApis(
  page: Page,
  overrides?: {
    stats?: typeof defaultStats;
    referred?: { instructors: unknown[]; total_count: number };
    popup?: typeof defaultPopupData;
  }
) {
  const stats = overrides?.stats ?? defaultStats;
  const referred = overrides?.referred ?? { instructors: [], total_count: 0 };
  const popup = overrides?.popup ?? defaultPopupData;

  await page.route('**/api/v1/auth/me', async (route) => {
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
      is_live: true,
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
          location_types: ['online'],
        },
      ],
      favorited_count: 0,
    });
  });

  await page.route('**/api/v1/addresses/service-areas/me', async (route) => {
    await respondJson(route, { items: [] });
  });

  await page.route('**/api/v1/payments/connect/status', async (route) => {
    await respondJson(route, {
      charges_enabled: true,
      payouts_enabled: true,
      details_submitted: true,
    });
  });

  await page.route('**/api/v1/payments/earnings', async (route) => {
    await respondJson(route, {
      total_earned: 0,
      total_fees: 0,
      booking_count: 0,
      average_earning: 0,
    });
  });

  await page.route('**/api/v1/messages/unread-count', async (route) => {
    await respondJson(route, { unread_count: 0, user_id: instructorUser.id });
  });

  await page.route('**/api/v1/conversations**', async (route) => {
    await respondJson(route, { conversations: [] });
  });

  await page.route('**/api/v1/bookings**', async (route) => {
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

  await page.route('**/api/v1/public/instructors/**/availability**', async (route) => {
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

  await page.route('**/api/v1/reviews/instructor/*/ratings', async (route) => {
    await respondJson(route, {
      overall: { rating: 4.5, total_reviews: 3, display_rating: '4.5' },
      by_service: [],
      confidence_level: 'trusted',
    });
  });

  await page.route('**/api/v1/instructor-referrals/stats', async (route) => {
    await respondJson(route, stats);
  });

  await page.route('**/api/v1/instructor-referrals/referred**', async (route) => {
    await respondJson(route, referred);
  });

  await page.route('**/api/v1/instructor-referrals/popup-data', async (route) => {
    await respondJson(route, popup);
  });

  await page.route('**/api/v1/instructor-referrals/founding-status', async (route) => {
    await respondJson(route, {
      is_founding_phase: true,
      total_founding_spots: 100,
      spots_filled: 58,
      spots_remaining: 42,
    });
  });
}

test.describe('Instructor Referrals', () => {
  test('shows referrals panel with sidebar and stats', async ({ page }) => {
    await bypassGateIfPresent(page, DEFAULT_BASE_URL, process.env.GATE_CODE);
    await page.goto(`${DEFAULT_BASE_URL}/instructor/dashboard?panel=referrals`);

    await expect(page.getByRole('heading', { name: 'Referrals' })).toBeVisible();
    await expect(page.getByText(/your referral link/i)).toBeVisible();
    await expect(page.getByText('https://instainstru.com/r/TESTCODE')).toBeVisible();

    await expect(page.getByText('Total referred')).toBeVisible();
    await expect(page.getByText('Pending payouts')).toBeVisible();
    await expect(page.getByText('Total earned')).toBeVisible();

    const sidebar = page.locator('aside');
    await expect(sidebar.getByText('Dashboard')).toBeVisible();
    await expect(sidebar.getByText('Bookings')).toBeVisible();
    await expect(sidebar.getByText('Earnings')).toBeVisible();
    await expect(sidebar.getByText('Availability')).toBeVisible();

    const referralNav = sidebar.getByRole('button', { name: 'Referrals' });
    await expect(referralNav).toHaveAttribute('aria-current', 'page');
    await expect(page.getByText('Founding Phase Bonus')).toBeVisible();
  });

  test('copy button updates state and clipboard', async ({ page }) => {
    await bypassGateIfPresent(page, DEFAULT_BASE_URL, process.env.GATE_CODE);
    await page.goto(`${DEFAULT_BASE_URL}/instructor/dashboard?panel=referrals`);

    const copyButton = page.getByRole('button', { name: /copy link/i });
    await copyButton.click();

    await expect(page.getByRole('button', { name: /copied/i })).toBeVisible();

    const copied = await page.evaluate(() => window.__copied);
    expect(copied).toBe('https://instainstru.com/r/TESTCODE');
  });
});

test.describe('Instructor Referral Popup', () => {
  test('popup appears and can be dismissed', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('instructor_referral_popup_dismissed');
    });

    await bypassGateIfPresent(page, DEFAULT_BASE_URL, process.env.GATE_CODE);
    await page.goto(`${DEFAULT_BASE_URL}/instructor/dashboard`);

    const popup = page.getByRole('dialog');
    await expect(popup).toBeVisible({ timeout: 6000 });
    await expect(page.getByText(/Earn \$75 Per Referral/i)).toBeVisible();

    await page.getByLabel('Close').click();
    await expect(popup).not.toBeVisible();

    const dismissed = await page.evaluate(() =>
      localStorage.getItem('instructor_referral_popup_dismissed')
    );
    expect(dismissed).toBe('true');
  });

  test('popup link navigates to referrals panel', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.removeItem('instructor_referral_popup_dismissed');
    });

    await bypassGateIfPresent(page, DEFAULT_BASE_URL, process.env.GATE_CODE);
    await page.goto(`${DEFAULT_BASE_URL}/instructor/dashboard`);

    const popup = page.getByRole('dialog');
    await expect(popup).toBeVisible({ timeout: 6000 });

    await page.getByRole('link', { name: /view all referrals/i }).click();
    await expect(page).toHaveURL(/panel=referrals/);
    await expect(page.getByRole('heading', { name: 'Referrals' })).toBeVisible();
  });
});
