import { expect, Page } from '@playwright/test';

const APP_SHELL_LOCATOR = 'header, nav, [data-app-shell="1"]';

export async function bypassGateIfPresent(page: Page, baseURL: string, gateCode?: string) {
  await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
  const gateInput = page.getByTestId('staff-gate-input');

  if ((await gateInput.count()) === 0) {
    console.info('[gate] no staff gate form found; skipping UI gate');
    return;
  }

  if (!gateCode) {
    console.info('[gate] staff gate present but no GATE_CODE provided; continuing without bypass');
    return;
  }

  // Fast path: token-based bypass (avoid logging secrets)
  try {
    await page.goto(`${baseURL}/?token=${encodeURIComponent(gateCode)}`, {
      waitUntil: 'domcontentloaded',
    });
    const hasCookie = await page
      .context()
      .cookies()
      .then((cookies) => cookies.some((cookie) => cookie.name === 'staff_access_token'));
    const appShell = page.locator(APP_SHELL_LOCATOR).first();
    if (hasCookie || (await appShell.isVisible({ timeout: 3000 }).catch(() => false))) {
      return;
    }
  } catch {
    // Fall through to UI flow
  }

  await page.goto(`${baseURL}/staff-login`, { waitUntil: 'domcontentloaded' });
  const loginInput = page.getByTestId('staff-gate-input');
  if ((await loginInput.count()) === 0) {
    console.info('[gate] staff login page missing gate input; skipping bypass');
    return;
  }

  await loginInput.fill(gateCode);
  await page.getByTestId('staff-gate-submit').click();
  await expect(page.locator(APP_SHELL_LOCATOR).first()).toBeVisible({ timeout: 10000 });
}
