import { test, expect } from '@playwright/test';

const HOSTS = [
  { fe: 'http://localhost:3000', api: 'http://localhost:8000' },
  { fe: 'http://beta-local.instainstru.com:3000', api: 'http://api.beta-local.instainstru.com:8000' },
];

test.describe('SameSite cookie smoke: /auth/me across local hosts', () => {
  for (const { fe, api } of HOSTS) {
    test(`me is 200 from FE ${fe} -> API ${api}`, async ({ browser }) => {
      test.skip(Boolean(process.env.CI) && !process.env.CI_LOCAL_E2E, 'Local-only smoke; opt-in via CI_LOCAL_E2E=1');

      const ctx = await browser.newContext({
        baseURL: fe,
      });
      const page = await ctx.newPage();

      await page.goto(`${fe}/login?smoke=1`);

      const email = `e2e-smoke+${Date.now()}@example.com`;
      const guest = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2);

      const loginResp = await page.evaluate(
        async ({ api, email, guest }) => {
          const r = await fetch(`${api}/auth/login-with-session`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, guest_session_id: guest }),
          });
          return { ok: r.ok, status: r.status };
        },
        { api, email, guest }
      );

      expect(loginResp.ok, `login status ${loginResp.status}`).toBeTruthy();

      const meResp = await page.evaluate(
        async ({ api }) => {
          const r = await fetch(`${api}/auth/me`, { credentials: 'include' });
          return { ok: r.ok, status: r.status };
        },
        { api }
      );

      expect(meResp.status).toBe(200);

      await ctx.close();
    });
  }
});
