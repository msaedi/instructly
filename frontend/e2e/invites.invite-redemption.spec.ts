import { test, expect } from '@playwright/test';
import { isAdmin } from './utils/projects';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isAdmin(workerInfo), `Admin-only spec (current project: ${workerInfo.project.name})`);
});

const CROSS_ORIGIN_ENABLED = process.env.E2E_CROSS_ORIGIN === '1';
const INVITES_ENABLED = process.env.CI_LOCAL_E2E === '1' || process.env.E2E_ENABLE_INVITES === '1';

test.skip(!CROSS_ORIGIN_ENABLED, 'Cross-origin E2E disabled (set E2E_CROSS_ORIGIN=1 to enable).');

test.use({ storageState: 'e2e/.storage/admin.json' });

test.describe('beta invite redemption across origins', () => {
  test('generate invite on preview and redeem on beta host', async ({ page, browser }) => {
    test.skip(!INVITES_ENABLED, 'Admin invite redemption disabled (set CI_LOCAL_E2E=1 or E2E_ENABLE_INVITES=1).');

    const projectBase = test.info().project.use?.baseURL ?? process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3100';
    const previewBase = process.env.E2E_PREVIEW_BASE_URL || projectBase;
    const betaBase = process.env.E2E_BETA_BASE_URL || previewBase;
    await page.goto(new URL('/admin/beta/invites', projectBase).toString(), { waitUntil: 'networkidle' });

    const inviteeEmail = `invitee+${Date.now()}@example.com`;
    const inviteEmailInput = page.getByTestId('invite-email-input');
    await inviteEmailInput.waitFor();
    await inviteEmailInput.fill(inviteeEmail);

    const sendInviteResponsePromise = page.waitForResponse(
      (response) =>
        response.url().includes('/api/beta/invites/send') &&
        response.request().method() === 'POST' &&
        response.status() === 200
    );

    await page.getByRole('button', { name: /send invite/i }).click();
    const sendInviteResponse = await sendInviteResponsePromise;
    const sendInviteJson = await sendInviteResponse.json();
    const inviteCode: string = String(sendInviteJson.code || sendInviteJson.invite?.code || '').trim();
    expect(inviteCode).toMatch(/^[A-Z0-9]{6,12}$/);

    await expect(page.getByTestId('invite-code-value')).toHaveText(inviteCode);

    const betaContext = await browser.newContext({ baseURL: betaBase });
    try {
      const betaPage = await betaContext.newPage();
      await betaPage.goto(`/instructor/join?email=${encodeURIComponent(inviteeEmail)}`, {
        waitUntil: 'domcontentloaded',
      });

      const codeInput = betaPage.getByTestId('invite-code-input');
      await codeInput.waitFor({ state: 'visible', timeout: 10_000 });
      await codeInput.click();
      await codeInput.fill('');
      await codeInput.type(inviteCode, { delay: 50 });
      await expect(codeInput).toHaveValue(inviteCode);

      const validateResponsePromise = betaPage.waitForResponse((response) => {
        const url = response.url();
        const matchesEndpoint =
          url.includes('/api/beta/invites/') &&
          (url.includes('/validate') || url.includes('/convert') || url.includes('/redeem'));
        return matchesEndpoint && response.request().method() === 'GET' && response.status() === 200;
      });

      await betaPage.getByRole('button', { name: /join!/i }).click();

      const validateResponse = await validateResponsePromise;
      expect(validateResponse.status()).toBeLessThan(400);
      const validateJson = await validateResponse.json();
      expect(validateJson).toMatchObject({ valid: true });

      await betaPage.waitForURL(/\/instructor\/welcome/i, { timeout: 15_000 });
      await expect(betaPage).toHaveURL(/\/instructor\/welcome/i);
      expect(betaPage.url()).toContain(inviteCode);
    } finally {
      await betaContext.close();
    }
  });
});
