import { test, expect, request } from '@playwright/test';

const base = process.env.PLAYWRIGHT_BASE_URL;

test.describe('env-contract smoke', () => {
  test.skip(!base, 'PLAYWRIGHT_BASE_URL not set');

  test('health headers', async () => {
    const ctx = await request.newContext({ baseURL: base });
    const res = await ctx.get('/health', { ignoreHTTPSErrors: true });
    expect(res.ok()).toBeTruthy();
    const xSiteMode = res.headers()['x-site-mode'];
    const xPhase = res.headers()['x-phase'];
    expect(['preview', 'prod']).toContain((xSiteMode || '').toLowerCase());
    expect(['beta', 'open']).toContain((xPhase || '').toLowerCase());
    await ctx.dispose();
  });

  test('CORS preflight allows credentials', async () => {
    const ctx = await request.newContext({ baseURL: base });
    const origin = 'https://example.com';
    const res = await ctx.fetch('/api/health', {
      method: 'OPTIONS',
      headers: {
        'Origin': origin,
        'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': 'content-type'
      }
    });
    expect(res.status()).toBeGreaterThanOrEqual(200);
    expect(res.status()).toBeLessThan(400);
    const allowCreds = res.headers()['access-control-allow-credentials'];
    expect((allowCreds || '').toLowerCase()).toBe('true');
    const echoed = res.headers()['access-control-allow-origin'];
    expect(echoed === origin).toBeTruthy();
    await ctx.dispose();
  });

  test('429 banner UX (skipped unless E2E_RATE_LIMIT_TEST=1)', async ({ page }) => {
    test.skip(process.env.E2E_RATE_LIMIT_TEST !== '1', 'Rate limit test disabled');
    await page.goto(base!);
    // Placeholder: assert presence of a 429 banner element if triggered
    // This is intentionally non-destructive and optional
    const banner = page.getByTestId('rate-limit-banner');
    await expect(banner).toBeVisible();
  });
});
