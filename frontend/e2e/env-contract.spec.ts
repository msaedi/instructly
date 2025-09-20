import { test, expect, request } from '@playwright/test';
import { bypassGateIfPresent } from './utils/gate';

const base = process.env.PLAYWRIGHT_BASE_URL;

test.describe('env-contract smoke', () => {
  test.skip(!base, 'PLAYWRIGHT_BASE_URL not set');

  test.beforeEach(async ({ page }) => {
    const code = process.env.GATE_CODE || '';
    await bypassGateIfPresent(page, base!, code || undefined);
  });

  test('health headers (gated)', async () => {
    test.skip(process.env.E2E_HEADERS_TEST !== '1', 'Headers test disabled');
    const ctx = await request.newContext({ baseURL: base });
    const res = await ctx.get('/health', { ignoreHTTPSErrors: true });
    expect(res.ok()).toBeTruthy();
    const xSiteMode = res.headers()['x-site-mode'];
    const xPhase = res.headers()['x-phase'];
    // Log for env-contract evidence
    console.info(`[headers] X-Site-Mode=${xSiteMode} X-Phase=${xPhase}`);
    expect(['preview', 'prod']).toContain((xSiteMode || '').toLowerCase());
    expect(['beta', 'open']).toContain((xPhase || '').toLowerCase());
    await ctx.dispose();
  });

  test('CORS preflight allows credentials (gated)', async () => {
    test.skip(process.env.E2E_HEADERS_TEST !== '1', 'Headers test disabled');
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
    // Log for env-contract evidence
    console.info(`[cors] access-control-allow-credentials=${allowCreds} access-control-allow-origin=${echoed}`);
    expect(echoed === origin).toBeTruthy();
    await ctx.dispose();
  });

  test('429 path triggers limited responses (gated)', async () => {
    test.skip(process.env.E2E_RATE_LIMIT_TEST !== '1', 'Rate limit test disabled');
    const ctx = await request.newContext({ baseURL: base });
    const dedupeKey = 'env-contract:rate-limit-test';
    // Hit the rate-limited endpoint several times quickly
    const attempts = 10;
    let limited = 0;
    for (let i = 0; i < attempts; i += 1) {
      const res = await ctx.get('/metrics/rate-limits/test?requests=1', { ignoreHTTPSErrors: true });
      if (res.status() === 429) limited += 1;
    }
    await ctx.dispose();
    // Log for triage
    console.info(`[429-triage] dedupeKey=${dedupeKey} limited=${limited} attempts=${attempts}`);
    // Expect exactly one deduped 429 signal
    expect(limited).toBe(1);
  });
});
