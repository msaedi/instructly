import { expect, test, type Page, type Route } from '@playwright/test';

import { bypassGateIfPresent } from './utils/gate';
import { mockAuthenticatedPageBackgroundApis } from './utils/authenticatedPageMocks';
import { isInstructor } from './utils/projects';

declare global {
  interface Window {
    __shared: ShareData | null;
    __copied: string | null;
  }
}

type NavShare = Navigator & {
  share?: (data?: ShareData) => Promise<void>;
  canShare?: (data?: ShareData) => boolean;
  clipboard?: Partial<Clipboard>;
};

test.use({ permissions: ['clipboard-read', 'clipboard-write'] });

test.beforeAll(({}, workerInfo) => {
  test.skip(
    !isInstructor(workerInfo),
    `Instructor-only spec (current project: ${workerInfo.project.name})`
  );
});

test.skip(Boolean(process.env.CI) && !process.env['CI_LOCAL_E2E'], 'local-only smoke; opt-in via CI_LOCAL_E2E=1');

const DEFAULT_BASE_URL = process.env['PLAYWRIGHT_BASE_URL'] || 'http://localhost:3100';

const instructorUser = {
  id: 'inst-user-1',
  email: 'sarah.chen@example.com',
  first_name: 'Sarah',
  last_name: 'Chen',
  roles: ['instructor'],
  permissions: [],
};

const dashboardPayload = {
  referral_code: 'FNVC6KDW',
  referral_link: 'https://beta.instainstru.com/r/FNVC6KDW',
  instructor_amount_cents: 5000,
  student_amount_cents: 2000,
  total_referred: 2,
  pending_payouts: 1,
  total_earned_cents: 7000,
  rewards: {
    pending: [
      {
        id: 'pending-1',
        amount_cents: 2000,
        date: '2026-03-21T10:00:00Z',
        failure_reason: null,
        payout_status: null,
        referee_first_name: 'Arlo',
        referee_last_initial: 'J',
        referral_type: 'student',
      },
    ],
    unlocked: [
      {
        id: 'unlocked-1',
        amount_cents: 5000,
        date: '2026-03-21T10:00:00Z',
        failure_reason: null,
        payout_status: 'pending',
        referee_first_name: 'Mina',
        referee_last_initial: 'T',
        referral_type: 'instructor',
      },
    ],
    redeemed: [
      {
        id: 'redeemed-1',
        amount_cents: 5000,
        date: '2026-03-21T10:00:00Z',
        failure_reason: null,
        payout_status: 'paid',
        referee_first_name: 'Nora',
        referee_last_initial: 'L',
        referral_type: 'instructor',
      },
    ],
  },
};

const fulfillJson = async (route: Route, body: unknown, status = 200) => {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
};

async function mockReferralPageApis(page: Page) {
  await page.route('**/api/v1/auth/me', async (route) => {
    await fulfillJson(route, instructorUser);
  });

  await page.route('**/instructors/me', async (route) => {
    await fulfillJson(route, {
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
        last_initial: 'C.',
        has_profile_picture: false,
      },
      services: [],
      favorited_count: 0,
    });
  });

  await page.route('**/api/v1/addresses/service-areas/me', async (route) => {
    await fulfillJson(route, { items: [] });
  });

  await page.route('**/api/v1/payments/connect/status', async (route) => {
    await fulfillJson(route, {
      charges_enabled: true,
      payouts_enabled: true,
      details_submitted: true,
    });
  });

  await page.route('**/api/v1/payments/earnings', async (route) => {
    await fulfillJson(route, {
      total_earned: 0,
      total_fees: 0,
      booking_count: 0,
      average_earning: 0,
    });
  });

  await page.route('**/api/v1/messages/unread-count', async (route) => {
    await fulfillJson(route, { unread_count: 0, user_id: instructorUser.id });
  });

  await page.route('**/api/v1/conversations**', async (route) => {
    await fulfillJson(route, { conversations: [] });
  });

  await page.route('**/api/v1/bookings**', async (route) => {
    await fulfillJson(route, { items: [], total: 0, page: 1, per_page: 50, has_next: false, has_prev: false });
  });

  await page.route('**/api/v1/instructor-referrals/dashboard', async (route) => {
    await fulfillJson(route, dashboardPayload);
  });
}

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
      }
    } catch {}
  });

  await mockAuthenticatedPageBackgroundApis(page, { userId: instructorUser.id });
  await mockReferralPageApis(page);
});

test.describe('Instructor Referrals', () => {
  test('shows the redesigned referrals panel inside the dashboard shell', async ({ page }) => {
    await bypassGateIfPresent(page, DEFAULT_BASE_URL, process.env['GATE_CODE']);
    await page.goto(`${DEFAULT_BASE_URL}/instructor/dashboard?panel=referrals`);

    await expect(page.getByRole('heading', { name: 'Referrals' })).toBeVisible();
    await expect(page.getByText('Refer an instructor')).toBeVisible();
    await expect(page.getByText('Refer a student')).toBeVisible();
    await expect(
      page.locator('input[aria-label="Your referral link"]')
    ).toHaveValue('https://beta.instainstru.com/r/FNVC6KDW');
    await expect(page.getByText('Total referred')).toBeVisible();
    await expect(page.getByText('Pending payouts')).toBeVisible();
    await expect(page.getByText('Total earned')).toBeVisible();
    await expect(page.getByText('No founding')).toHaveCount(0);

    const sidebar = page.locator('aside');
    await expect(sidebar.getByText('Dashboard')).toBeVisible();
    await expect(sidebar.getByText('Bookings')).toBeVisible();
    await expect(sidebar.getByText('Earnings')).toBeVisible();

    const referralNav = sidebar.getByRole('button', { name: 'Referrals' });
    await expect(referralNav).toHaveAttribute('aria-current', 'page');
  });

  test('copy and share actions use the referral link', async ({ page }) => {
    await bypassGateIfPresent(page, DEFAULT_BASE_URL, process.env['GATE_CODE']);
    await page.goto(`${DEFAULT_BASE_URL}/instructor/dashboard?panel=referrals`);

    await page.getByRole('button', { name: 'Copy referral link' }).click();
    await expect.poll(() => page.evaluate(() => window.__copied)).toBe(
      'https://beta.instainstru.com/r/FNVC6KDW'
    );

    await page.getByRole('button', { name: 'Share referral link' }).click();
    await expect
      .poll(() => page.evaluate(() => window.__shared?.url ?? null))
      .toBe('https://beta.instainstru.com/r/FNVC6KDW');
  });
});
