import { Page, expect } from '@playwright/test';

export async function bypassGateIfPresent(page: Page, baseURL: string, gateCode?: string) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });

  const form = page.locator('[data-testid="staff-gate-form"]').first();
  const visible = await form.isVisible().catch(() => false);
  if (!visible) return;

  if (!gateCode) throw new Error('Gate present but no GATE_CODE provided');

  await page.getByTestId('staff-gate-input').fill(gateCode);
  await page.getByTestId('staff-gate-submit').click();

  await expect(page.locator('header, nav, [data-app-shell="1"]').first()).toBeVisible({ timeout: 10000 });
}
