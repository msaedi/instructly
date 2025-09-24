import { test, expect } from '@playwright/test';

const PREVIEW_BASE = 'http://localhost:3000';
const BETA_BASE = 'http://beta-local.instainstru.com:3000';
const ADMIN_EMAIL = 'admin@instainstru.com';
const ADMIN_PASSWORD = 'Test1234';

test.describe('beta invite redemption across origins', () => {
  test('generate invite on preview and redeem on beta host', async ({ page, browser }) => {
    test.skip(process.env.CI_LOCAL_E2E !== '1', 'Only runs when CI_LOCAL_E2E=1');

    // 1. Login to preview admin
    await page.goto(`${PREVIEW_BASE}/login`, { waitUntil: 'domcontentloaded' });
    await page.getByLabel('Email').fill(ADMIN_EMAIL);
    await page.getByLabel('Password').fill(ADMIN_PASSWORD);

    const loginResponsePromise = page.waitForResponse((response) => {
      return response.url().includes('/auth/login') && response.request().method() === 'POST';
    });

    await page.getByRole('button', { name: /log in|sign in|submit/i }).click();

    const loginResponse = await loginResponsePromise;
    expect(loginResponse.ok()).toBeTruthy();
    const loginJson = await loginResponse.json();
    expect(loginJson.requires_2fa).toBeFalsy();

    // Allow client-side auth check to complete before navigation
    await page.waitForTimeout(500);

    // 2. Navigate to beta invite admin and generate invite
    await page.goto(`${PREVIEW_BASE}/admin/beta/invites`, { waitUntil: 'networkidle' });

    const inviteeEmail = `invitee+${Date.now()}@example.com`;
    await page.getByLabel('Email').fill(inviteeEmail);

    const sendInviteResponsePromise = page.waitForResponse((response) => {
      return response.url().includes('/api/beta/invites/send') && response.request().method() === 'POST';
    });

    await page.getByRole('button', { name: /send invite/i }).click();

    const sendInviteResponse = await sendInviteResponsePromise;
    expect(sendInviteResponse.ok()).toBeTruthy();
    const sendInviteJson = await sendInviteResponse.json();
    const inviteCode: string = String(sendInviteJson.code || sendInviteJson.invite?.code || '');
    expect(inviteCode).toMatch(/^[A-Z0-9]{6,12}$/);

    // Ensure the code is visible in the UI for manual confirmation/debugging
    await expect(page.getByText(inviteCode)).toBeVisible();

    // 3. Switch to beta-local origin in a clean context
    const betaContext = await browser.newContext({ baseURL: BETA_BASE });
    try {
      const betaPage = await betaContext.newPage();
      await betaPage.goto('/instructor/join', { waitUntil: 'domcontentloaded' });

      await betaPage.getByLabel('Enter your founding instructor code').fill(inviteCode);

      const validateResponsePromise = betaPage.waitForResponse((response) => {
        return response.url().includes('/api/beta/invites/validate') && response.request().method() === 'GET';
      });

      await betaPage.getByRole('button', { name: /continue/i }).click();

      const validateResponse = await validateResponsePromise;
      expect(validateResponse.status()).toBeLessThan(400);
      const corsOrigin = validateResponse.headers()['access-control-allow-origin'];
      expect(corsOrigin).toBe(BETA_BASE);
      const corsCreds = validateResponse.headers()['access-control-allow-credentials'];
      expect((corsCreds || '').toLowerCase()).toBe('true');
      const validateJson = await validateResponse.json();
      expect(validateJson).toMatchObject({ valid: true });

      await betaPage.waitForURL(/\/instructor\/welcome/i);
      await expect(betaPage).toHaveURL(/\/instructor\/welcome/i);
      expect(betaPage.url()).toContain(inviteCode);
    } finally {
      await betaContext.close();
    }
  });
});
