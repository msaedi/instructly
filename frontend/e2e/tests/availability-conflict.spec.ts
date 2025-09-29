import { test, expect } from '@playwright/test';

test.describe('Availability 409 conflict flow', () => {
  test('shows friendly modal and refreshes on confirm', async ({ browser }) => {
    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    // Simulate logged-in instructor in both contexts
    for (const p of [pageA, pageB]) {
      await p.addInitScript(() => {
        localStorage.setItem('access_token', 'e2e_token');
      });
      await p.route('**/auth/me', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            id: '01TESTUSERINSTRUCTOR00000000001',
            email: 'instructor@example.com',
            first_name: 'Test',
            last_name: 'Instructor',
            roles: ['instructor'],
            is_active: true,
          }),
        });
      });
      // Minimal profile endpoint if requested
      await p.route('**/instructors/me', async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ user_id: '01TESTUSERINSTRUCTOR00000000001', user: { first_name: 'Test', last_initial: 'I' } }),
        });
      });
      // Detailed slots fetch (week range list)
      await p.route(/.*\/instructors\/availability\/\?start_date=.*/, async (route) => {
        await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([]) });
      });
      // Week GET returns empty schedule with ETag/Last-Modified
      await p.route(/.*\/instructors\/availability\/week\?start_date=.*/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: {
            'ETag': 'v1',
            'Last-Modified': new Date().toUTCString(),
          },
          body: JSON.stringify({}),
        });
      });
    }

    // Login or set auth if helpers exist; here we assume already authenticated via dev setup
    await pageA.goto('/instructor/availability');
    await pageB.goto('/instructor/availability');

    // Wait for page to load headers (disambiguate to the H1)
    await expect(pageA.getByRole('heading', { name: 'Set Availability' })).toBeVisible();
    await expect(pageB.getByRole('heading', { name: 'Set Availability' })).toBeVisible();

    // On page A: make a change and save to create a new version (mock POST 200)
    await pageA.route('**/instructors/availability/week', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          headers: { 'ETag': 'v2', 'Last-Modified': new Date().toUTCString() },
          body: JSON.stringify({
            message: 'Saved weekly availability',
            week_start: '2025-08-25',
            week_end: '2025-08-31',
            windows_created: 1,
            windows_updated: 0,
            windows_deleted: 0,
          }),
        });
      } else {
        await route.continue();
      }
    });
    const firstCellA = pageA.locator('[data-cell]').first();
    const savePostA = pageA.waitForResponse((res) =>
      res.url().includes('/instructors/availability/week') && res.request().method() === 'POST'
    );
    await firstCellA.click();
    const responseA = await savePostA;
    expect(responseA.status()).toBe(200);

    // On page B: make a conflicting change and attempt to save, expecting conflict modal (mock POST 409)
    await pageB.route('**/instructors/availability/week', async (route) => {
      if (route.request().method() === 'POST') {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Week has changed; please refresh and retry' }),
        });
      } else {
        await route.continue();
      }
    });
    const firstCellB = pageB.locator('[data-cell]').nth(1);
    const savePostB = pageB.waitForResponse((res) =>
      res.url().includes('/instructors/availability/week') && res.request().method() === 'POST'
    );
    await firstCellB.click();
    const responseB = await savePostB;
    expect(responseB.status()).toBe(409);

    // Expect modal
    await expect(pageB.getByRole('dialog')).toBeVisible();
    await expect(pageB.getByRole('button', { name: /refresh/i })).toBeVisible();

    // Confirm refresh
    await pageB.getByRole('button', { name: /refresh/i }).click();
    await expect(pageB.getByRole('dialog')).toBeHidden();

    await contextA.close();
    await contextB.close();
  });
});
