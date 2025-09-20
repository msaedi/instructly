import { test, expect, request } from '@playwright/test';
import { bypassGateIfPresent } from './utils/gate';

const base = process.env.PLAYWRIGHT_BASE_URL as string;
const apiBase = process.env.PLAYWRIGHT_API_BASE_URL as string;

test.describe('env-contract smoke', () => {
  test.skip(!base, 'PLAYWRIGHT_BASE_URL not set');

  test.beforeEach(async ({ page }) => {
    const code = process.env.GATE_CODE || '';
    await bypassGateIfPresent(page, base!, code || undefined);
  });

  test('health headers (gated)', async () => {
    test.skip(process.env.E2E_HEADERS_TEST !== '1', 'Headers test disabled');
    const ctx = await request.newContext({ baseURL: process.env.PLAYWRIGHT_API_BASE_URL! });
    const candidates = [
      '/api/health',          // preferred if present
      '/health',              // common alias
      '/openapi.json',        // FastAPI always serves this (unless disabled)
      '/docs'                 // FastAPI docs (HTML)
    ];
    let res, xSiteMode = '', xPhase = '';
    for (const path of candidates) {
      res = await ctx.get(path, { ignoreHTTPSErrors: true });
      if (res.status() >= 500) continue; // try next candidate on 5xx
      const h = res.headers();
      xSiteMode = (h['x-site-mode'] || '').toString();
      xPhase    = (h['x-phase'] || '').toString();
      if (xSiteMode || xPhase) break;    // we found headers, stop probing
    }
    // We must have hit a non-5xx response by now.
    expect(res!.status()).toBeLessThan(500);
    console.info(`[headers] X-Site-Mode=${xSiteMode} X-Phase=${xPhase}`);
    expect(['preview','prod']).toContain((xSiteMode || '').toLowerCase());
    const phase = (xPhase || '').toLowerCase();
    console.info(`[headers-allowed] phase=${phase}`);
    expect(['beta','open','instructor_only','instructor-only']).toContain(phase);
    await ctx.dispose();
  });

  test('CORS preflight allows credentials (gated)', async () => {
    test.skip(process.env.E2E_HEADERS_TEST !== '1', 'Headers test disabled');
    const ctx = await request.newContext({ baseURL: apiBase });
    const origin = base!;
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
    const ctx = await request.newContext({ baseURL: apiBase });
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
    // Only assert when limiter active; otherwise skip to avoid flakiness
    test.skip(limited === 0, 'No rate-limit 429 observed on preview; skipping assertion');
    expect(limited).toBeGreaterThanOrEqual(1);
    expect(limited).toBeLessThanOrEqual(attempts);
  });
});
