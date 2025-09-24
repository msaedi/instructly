import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { bypassGateIfPresent } from './utils/gate';

declare global {
  interface Window {
    __shared: ShareData | null;
    __copied: string | null;
  }

  interface Navigator {
    canShare?: (data?: ShareData) => boolean;
    share?: (data?: ShareData) => Promise<void>;
  }
}

test.use({ permissions: ['clipboard-read', 'clipboard-write'] });

test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    window.__shared = null;
    window.__copied = null;

    try {
      Object.defineProperty(navigator, 'canShare', {
        configurable: true,
        value: () => true,
      });
    } catch {}

    try {
      Object.defineProperty(navigator, 'share', {
        configurable: true,
        value: (data?: ShareData) => {
          window.__shared = data ?? {};
          return Promise.resolve();
        },
      });
    } catch {}

    try {
      if (!('clipboard' in navigator)) {
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: {
            writeText: (text: string) => {
              window.__copied = text;
              return Promise.resolve();
            },
            readText: () => Promise.resolve(''),
          },
        });
      } else if (navigator.clipboard) {
        Object.defineProperty(navigator.clipboard, 'writeText', {
          configurable: true,
          value: (text: string) => {
            window.__copied = text;
            return Promise.resolve();
          },
        });

        if (!navigator.clipboard.readText) {
          Object.defineProperty(navigator.clipboard, 'readText', {
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

    await page.route('**/api/referrals/me', async (route) => {
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
    await page.goto(`${base}/rewards`, { waitUntil: 'networkidle' });
    await expect(page.getByRole('heading', { name: 'Your rewards' })).toBeVisible();

    const axe = new AxeBuilder({ page }).include('main');
    const results = await axe.analyze();
    expect(results.violations).toEqual([]);

    await page.waitForLoadState('domcontentloaded');
    await expect(page).toHaveURL(/\/rewards/);

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

    await page.goto(`${base}/referral`, { waitUntil: 'networkidle' });
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

    await page.goto(`${base}/checkout?orderId=ORDER-PROMO&subtotalCents=9000&promo=1`, { waitUntil: 'networkidle' });
    await expect(page.getByText('Referral credit can’t be combined with other promotions.')).toBeVisible();
    await expect(page.getByRole('button', { name: /apply referral credit/i })).toBeDisabled();

    await page.goto(`${base}/checkout?orderId=ORDER-SMALL&subtotalCents=5000`, { waitUntil: 'networkidle' });
    await expect(page.getByText('Spend $75+ to use your $20 credit.')).toBeVisible();

    await page.route('**/api/referrals/checkout/apply-referral', async (route) => {
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

    await page.goto(`${base}/checkout?orderId=ORDER-OK&subtotalCents=9000`, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: /apply referral credit/i }).click();
    const appliedMessage = page.locator('p', { hasText: 'Referral credit applied' }).first();
    await expect(appliedMessage).toBeVisible();

    await page.unroute('**/api/referrals/checkout/apply-referral');
  });
});
