import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'fs';
import path from 'path';
import { bypassGateIfPresent } from './utils/gate';

function parseImpacts(env?: string) {
  return (env ?? 'critical')
    .split(',')
    .map(s => s.trim().toLowerCase())
    .filter(Boolean);
}

function loadBaseline(): Set<string> {
  try {
    const filePath = path.join(__dirname, 'a11y-baseline.json');
    if (!fs.existsSync(filePath)) {
      return new Set();
    }
    const raw = fs.readFileSync(filePath, 'utf8');
    if (!raw.trim()) {
      return new Set();
    }
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) {
      return new Set(parsed.filter((item): item is string => typeof item === 'string'));
    }
    if (parsed && typeof parsed === 'object') {
      return new Set(Object.keys(parsed as Record<string, unknown>));
    }
    return new Set();
  } catch (error) {
    console.warn('[a11y] failed to load baseline, proceeding without it', error);
    return new Set();
  }
}

test('home a11y smoke (logs by default; fails only when A11Y_STRICT=1)', async ({ page }) => {
  const base = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';
  const strictEnv = process.env.A11Y_STRICT ?? process.env.E2E_A11Y_STRICT ?? '0';
  const strict = strictEnv.trim() === '1';
  const impacts = parseImpacts(process.env.A11Y_IMPACTS);
  const baseline = loadBaseline();

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
  const fingerprints = filtered.map(v => {
    const firstTarget = v.nodes?.[0]?.target?.[0] ?? 'unknown';
    return `${v.id}::${firstTarget}`;
  });
  const newViolations = fingerprints.filter(fp => !baseline.has(fp));

  // Log concise summary for CI artifacts / local debugging
  console.info(
    `[a11y] scope=${includeSelector ?? 'body'} total=${results.violations.length} filtered(${impacts.join(',')})=${filtered.length} new=${newViolations.length}`
  );
  for (const v of filtered.slice(0, 10)) {
    const nodes = v.nodes?.length ?? 0;
    console.info(`[a11y-violation] id=${v.id} impact=${v.impact} nodes=${nodes}`);
  }
  for (const fp of newViolations) {
    console.info(`[a11y-new] ${fp}`);
  }

  if (strict) {
    expect(newViolations).toEqual([]);            // enforce only when strict
  } else {
    expect(true).toBe(true);                 // informative-only by default
  }
});
