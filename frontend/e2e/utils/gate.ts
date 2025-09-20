import { Page } from '@playwright/test';

export async function bypassGateIfPresent(page: Page, baseURL: string, code: string) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  const input = page.getByTestId('staff-gate-input');
  if ((await input.count()) === 0) {
    console.info('[gate] no staff gate form found; skipping UI gate');
    return;
  }
  await input.fill(code);
  await page.getByTestId('staff-gate-submit').click();
  // Don’t assert app-shell here; just allow nav to settle.
  await page.waitForLoadState('networkidle', { timeout: 10000 });
}
