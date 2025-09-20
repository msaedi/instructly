import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { bypassGateIfPresent } from './utils/gate';

function parseImpacts(env?: string) {
  return (env ?? 'critical')
    .split(',')
    .map(s => s.trim().toLowerCase())
    .filter(Boolean);
}

test('home a11y smoke (logs by default; fails only when A11Y_STRICT=1)', async ({ page }) => {
  const base = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';
  const strict = (process.env.A11Y_STRICT ?? '0').trim() === '1';
  const impacts = parseImpacts(process.env.A11Y_IMPACTS);

  await bypassGateIfPresent(page, base, process.env.GATE_CODE);
  await page.goto(base + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(100);

  // Prefer a main-like region; fallback to body
  const CANDIDATES = ['main', '[role="main"]', '[data-testid="app-main"]'];
  let includeSelector: string | null = null;
  for (const sel of CANDIDATES) {
    const el = await page.$(sel);
    if (el) { includeSelector = sel; break; }
  }

  let builder = new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']);
  if (includeSelector) builder = builder.include(includeSelector);

  const results = await builder.analyze();
  const filtered = results.violations.filter(v => impacts.includes((v.impact || '').toLowerCase()));

  // Log concise summary for CI artifacts / local debugging
  console.info(`[a11y] scope=${includeSelector ?? 'body'} total=${results.violations.length} filtered(${impacts.join(',')})=${filtered.length}`);
  for (const v of filtered.slice(0, 10)) {
    const nodes = v.nodes?.length ?? 0;
    console.info(`[a11y-violation] id=${v.id} impact=${v.impact} nodes=${nodes}`);
  }

  if (strict) {
    expect(filtered).toEqual([]);            // enforce only when strict
  } else {
    expect(true).toBe(true);                 // informative-only by default
  }
});
