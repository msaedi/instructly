import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { bypassGateIfPresent } from './utils/gate';

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

test.beforeEach(async ({ context }) => {
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
  });
});

test.describe('Referral surfaces', () => {
  test('rewards page share + copy works and passes axe smoke', async ({ page }) => {
    const base = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';

    await page.route('**/api/v1/referrals/me', async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204 });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          code: 'MYFRIEND',
          share_url: `${base}/r/myfriend`,
          pending: [],
          unlocked: [
            {
              id: 'reward-1',
              amount_cents: 2000,
              status: 'unlocked',
              side: 'student',
              created_at: new Date().toISOString(),
              unlock_ts: null,
              expire_ts: new Date(Date.now() + 1000 * 60 * 60 * 24 * 10).toISOString(),
            },
          ],
          redeemed: [],
          expiry_notice_days: [14, 3],
        }),
      });
    });

    await bypassGateIfPresent(page, base, process.env.GATE_CODE);

    const studentEmail = process.env.E2E_STUDENT_EMAIL || 'john.smith@example.com';
    const studentPassword = process.env.E2E_STUDENT_PASSWORD || 'TestPassword123!';

    await page.route('**/api/v1/auth/login', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: {
            'set-cookie': 'access_token=playwright-token; Path=/; HttpOnly; SameSite=Lax',
          },
          body: JSON.stringify({
            requires_2fa: false,
          }),
        });
        return;
      }
      await route.continue();
    });

    await page.route('**/api/v1/auth/login-with-session', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: {
            'set-cookie': 'access_token=playwright-token; Path=/; HttpOnly; SameSite=Lax',
          },
          body: JSON.stringify({
            requires_2fa: false,
          }),
        });
        return;
      }
      await route.continue();
    });

    const authMeResponse = {
      id: 'playwright-student',
      email: studentEmail,
      first_name: 'Playwright',
      last_name: 'Student',
      roles: ['student'],
      permissions: [],
      credits_balance: 2000,
    };

    await page.route('**/api/v1/auth/me', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(authMeResponse),
        });
        return;
      }
      await route.continue();
    });

    await page.route('**/api/api/v1/auth/me', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(authMeResponse),
        });
        return;
      }
      await route.continue();
    });

    await page.route('**/api/v1/addresses/me', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [] }),
        });
        return;
      }
      await route.continue();
    });

    await page.route('**/api/v1/2fa/status', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ enabled: false, verified_at: null, last_used_at: null }),
        });
        return;
      }
      await route.continue();
    });

    await page.goto(`${base}/login`, { waitUntil: 'domcontentloaded' });
    await page.getByLabel(/email/i).fill(studentEmail);
    await page.getByLabel(/password/i).fill(studentPassword);
    await page.getByRole('button', { name: /log in|sign in|submit/i }).click();
    await page.waitForTimeout(500);

    await page.goto(`${base}/student/dashboard?tab=rewards`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByRole('heading', { name: 'Your rewards' })).toBeVisible();
    await expect(page.getByRole('button', { name: /send invites/i })).toBeVisible();

    const axe = new AxeBuilder({ page }).include('main');
    const results = await axe.analyze();
    expect(results.violations).toEqual([]);

    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/student\/dashboard\?tab=rewards$/);

    const shareButton = page.getByRole('button', { name: /^share$/i }).first();
    await expect(shareButton).toBeVisible();
    await shareButton.click();

    await page.waitForFunction(() => Boolean(window.__shared) || Boolean(window.__copied));

    type ShareCopyResult = { shared: ShareData | null; copied: string | null };

    const result = await page.evaluate<ShareCopyResult>(() => ({
      shared: window.__shared,
      copied: window.__copied,
    }));

    expect(result.shared || result.copied).toBeTruthy();
    if (result.shared) {
      expect(result.shared).toMatchObject({
        title: expect.anything(),
        text: expect.anything(),
        url: expect.anything(),
      });
    }
  });

  test('referral landing page renders and passes axe smoke', async ({ page }) => {
    const base = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';
    await bypassGateIfPresent(page, base, process.env.GATE_CODE);

    await page.goto(`${base}/referral`, { waitUntil: 'domcontentloaded' });
    await expect(
      page.getByRole('heading', { name: 'Book your first $75+ lesson and get $20 off.' })
    ).toBeVisible();

    const axe = new AxeBuilder({ page }).include('main');
    const results = await axe.analyze();
    expect(results.violations).toEqual([]);
  });

  test('checkout panel enforces eligibility states', async ({ page }) => {
    const base = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';
    await bypassGateIfPresent(page, base, process.env.GATE_CODE);

    await page.goto(`${base}/checkout?orderId=ORDER-PROMO&subtotalCents=9000&promo=1`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Referral credit can’t be combined with other promotions.').first()).toBeVisible();
    await expect(page.getByRole('button', { name: /apply referral credit/i })).toHaveCount(0);

    await page.goto(`${base}/checkout?orderId=ORDER-SMALL&subtotalCents=5000`, { waitUntil: 'domcontentloaded' });
    await expect(page.getByText('Spend $75+ to use your $20 credit.')).toBeVisible();

    // Match both direct API calls and proxied calls (e.g., /api/proxy/api/v1/...)
    const routePattern = /referrals\/checkout\/apply-referral/;
    await page.route(routePattern, async (route) => {
      if (route.request().method() === 'OPTIONS') {
        await route.fulfill({ status: 204 });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ applied_cents: 2000 }),
      });
    });

    // Use 'load' to ensure full page load including React hydration
    await page.goto(`${base}/checkout?orderId=ORDER-OK&subtotalCents=9000`, { waitUntil: 'load' });
    const applyButton = page.getByRole('button', { name: /apply referral credit/i });
    await expect(applyButton).toBeVisible({ timeout: 10000 });
    await expect(applyButton).toBeEnabled({ timeout: 5000 });
    // Wait for React hydration to complete
    await page.waitForTimeout(500);

    await applyButton.click();
    await expect(page.getByText('Referral credit applied').first()).toBeVisible({ timeout: 10000 });

    await page.unroute(routePattern);
  });
});
