import { randomUUID } from 'node:crypto';
import { test, expect } from '@playwright/test';

const LIVE_MODE = Boolean(process.env.E2E_APP_ORIGIN && process.env.E2E_API_ORIGIN);
const APP_ORIGIN = process.env.E2E_APP_ORIGIN ?? 'http://localhost:3100';
const API_ORIGIN = process.env.E2E_API_ORIGIN ?? 'http://localhost:8000';
const TEST_PASSWORD = process.env.E2E_SMOKE_PASSWORD ?? 'Test1234!';

const generateGuestId = (): string => {
  try {
    return randomUUID();
  } catch {
    return Math.random().toString(36).slice(2);
  }
};

test.skip(Boolean(process.env.CI) && !process.env.CI_LOCAL_E2E, 'local-only smoke; opt-in via CI_LOCAL_E2E=1');

test('preferred places: add two -> save -> reload -> persisted', async ({ page }) => {

  const fulfillJson = async (
    route: import('@playwright/test').Route,
    body: unknown,
    status = 200
  ): Promise<void> => {
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  };

  if (!LIVE_MODE) {
    const state = {
      preferredTeaching: [] as Array<{ address: string; label?: string }>,
      preferredPublic: [] as Array<{ address: string }>,
    };

    await page.route('**/auth/register', (route) => fulfillJson(route, { ok: true }));
    await page.route('**/auth/login-with-session', (route) => fulfillJson(route, { ok: true }));

    await page.route('**/auth/me', (route) =>
      fulfillJson(route, {
        id: 'mock-user',
        first_name: 'E2E',
        last_name: 'Tester',
        zip_code: '10001',
        roles: ['instructor'],
      })
    );

    await page.route('**/instructors/me', async (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        return fulfillJson(route, {
          bio: 'Mock instructor bio for preferred places smoke.',
          service_area_summary: 'Manhattan',
          service_area_boroughs: ['Manhattan'],
          service_area_neighborhoods: [
            {
              neighborhood_id: 'mock-manhattan',
              name: 'Manhattan',
              borough: 'Manhattan',
            },
          ],
          years_experience: 5,
          min_advance_booking_hours: 2,
          buffer_time_minutes: 0,
          preferred_teaching_locations: state.preferredTeaching,
          preferred_public_spaces: state.preferredPublic,
          user: {
            id: 'mock-user',
            first_name: 'E2E',
            last_name: 'Tester',
            zip_code: '10001',
          },
        });
      }
      if (method === 'PUT') {
        let data: Record<string, unknown> = {};
        try {
          data = route.request().postDataJSON();
        } catch {
          data = {};
        }
        const teachingRaw = Array.isArray(data?.preferred_teaching_locations)
          ? (data.preferred_teaching_locations as Array<Record<string, unknown>>)
          : [];
        const teachingParsed: Array<{ address: string; label?: string }> = [];
        for (const entry of teachingRaw) {
          const address = typeof entry?.address === 'string' ? entry.address.trim() : '';
          if (!address) continue;
          const label = typeof entry?.label === 'string' ? entry.label.trim() : undefined;
          teachingParsed.push(label ? { address, label } : { address });
          if (teachingParsed.length === 2) break;
        }
        state.preferredTeaching = teachingParsed;

        const publicRaw = Array.isArray(data?.preferred_public_spaces)
          ? (data.preferred_public_spaces as Array<Record<string, unknown>>)
          : [];
        const publicParsed: Array<{ address: string }> = [];
        for (const entry of publicRaw) {
          const address = typeof entry?.address === 'string' ? entry.address.trim() : '';
          if (!address) continue;
          publicParsed.push({ address });
          if (publicParsed.length === 2) break;
        }
        state.preferredPublic = publicParsed;

        return fulfillJson(route, {
          bio: data?.bio ?? 'Mock instructor bio for preferred places smoke.',
          service_area_summary: 'Manhattan',
          service_area_boroughs: ['Manhattan'],
          service_area_neighborhoods: [
            {
              neighborhood_id: 'mock-manhattan',
              name: 'Manhattan',
              borough: 'Manhattan',
            },
          ],
          years_experience: data?.years_experience ?? 5,
          min_advance_booking_hours: data?.min_advance_booking_hours ?? 2,
          buffer_time_minutes: data?.buffer_time_minutes ?? 0,
          preferred_teaching_locations: state.preferredTeaching,
          preferred_public_spaces: state.preferredPublic,
        });
      }
      return route.continue();
    });

    await page.route('**/api/addresses/me', (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        return fulfillJson(route, {
          items: [
            {
              id: 'addr-1',
              is_default: true,
              postal_code: '10001',
              street_line1: '123 Mock St',
              locality: 'New York',
              administrative_area: 'NY',
              country_code: 'US',
            },
          ],
          total: 1,
        });
      }
      if (method === 'POST' || method === 'PATCH' || method === 'DELETE') {
        return fulfillJson(route, { ok: true });
      }
      return fulfillJson(route, {});
    });

    await page.route('**/api/addresses/zip/is-nyc*', (route) =>
      fulfillJson(route, { is_nyc: true, borough: 'Manhattan' })
    );

    await page.route('**/api/addresses/service-areas/me', (route) => {
      const method = route.request().method();
      if (method === 'GET') {
        return fulfillJson(route, { items: [], total: 0 });
      }
      if (method === 'PUT') {
        return fulfillJson(route, { items: [], total: 0 });
      }
      return fulfillJson(route, { items: [], total: 0 });
    });

    await page.route('**/api/addresses/regions/neighborhoods*', (route) =>
      fulfillJson(route, { items: [], total: 0, page: 1, per_page: 0 })
    );

    await page.route('**/api/addresses/places/autocomplete*', (route) =>
      fulfillJson(route, { items: [] })
    );
  } else {
    const email = `e2e-places+${Date.now()}@example.com`;
    const guest = generateGuestId();

    const registerResp = await page.evaluate(
      async ({ api, email, guest, password }) => {
        const payload = {
          email,
          password,
          first_name: 'E2E',
          last_name: 'Tester',
          zip_code: '10001',
          role: 'instructor',
          guest_session_id: guest,
        };
        const response = await fetch(`${api}/auth/register`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const errorBody = response.ok ? undefined : await response.text();
        return { ok: response.ok, status: response.status, body: errorBody };
      },
      { api: API_ORIGIN, email, guest, password: TEST_PASSWORD }
    );

    expect(
      registerResp.ok,
      `register status ${registerResp.status}${registerResp.body ? `: ${registerResp.body}` : ''}`
    ).toBeTruthy();

    const loginResp = await page.evaluate(
      async ({ api, email, guest, password }) => {
        const response = await fetch(`${api}/auth/login-with-session`, {
          method: 'POST',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email, password, guest_session_id: guest }),
        });
        const errorBody = response.ok ? undefined : await response.text();
        return { ok: response.ok, status: response.status, body: errorBody };
      },
      { api: API_ORIGIN, email, guest, password: TEST_PASSWORD }
    );

    expect(
      loginResp.ok,
      `login status ${loginResp.status}${loginResp.body ? `: ${loginResp.body}` : ''}`
    ).toBeTruthy();

    const seedResp = await page.evaluate(
      async ({ api }) => {
        const payload = {
          bio: 'E2E seed biography for preferred places smoke test.',
          years_experience: 5,
          min_advance_booking_hours: 2,
          buffer_time_minutes: 0,
          preferred_teaching_locations: [],
          preferred_public_spaces: [],
        };
        const response = await fetch(`${api}/instructors/me`, {
          method: 'PUT',
          credentials: 'include',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const errorBody = response.ok ? undefined : await response.text();
        return { ok: response.ok, status: response.status, body: errorBody };
      },
      { api: API_ORIGIN }
    );

    expect(seedResp.ok, `seed status ${seedResp.status}${seedResp.body ? `: ${seedResp.body}` : ''}`).toBeTruthy();
  }

  await page.goto(`${APP_ORIGIN}/instructor/profile`);
  await page.waitForURL('**/instructor/profile**');
  await page.waitForLoadState('networkidle');

  const teachingInput = page.getByTestId('ptl-input');
  await teachingInput.waitFor();

  await teachingInput.fill('1 Bryant Park, New York, NY');
  await page.getByTestId('ptl-add').click();
  await page.getByTestId('ptl-chip-0').waitFor();
  await page.getByTestId('ptl-chip-label-0').fill('Office');

  await teachingInput.fill('320 E 46th St, New York, NY');
  await page.getByTestId('ptl-add').click();
  await page.getByTestId('ptl-chip-1').waitFor();
  await page.getByTestId('ptl-chip-label-1').fill('Home');

  const publicInput = page.getByTestId('pps-input');
  await publicInput.fill('New York Public Library');
  await page.getByTestId('pps-add').click();
  await page.getByTestId('pps-chip-0').waitFor();

  await publicInput.fill('Times Square');
  await page.getByTestId('pps-add').click();
  await page.getByTestId('pps-chip-1').waitFor();

  const saveResponsePromise = page.waitForResponse((response) =>
    response.url().endsWith('/instructors/me') &&
    response.request().method() === 'PUT' &&
    response.status() === 200
  );

  await Promise.all([
    saveResponsePromise,
    page.getByRole('button', { name: /save & continue/i }).click(),
  ]);

  await page.waitForURL('**/instructor/onboarding/skill-selection**');

  await page.goto(`${APP_ORIGIN}/instructor/profile`);
  await page.waitForURL('**/instructor/profile**');
  await page.waitForLoadState('networkidle');

  await expect(page.getByTestId('ptl-chip-0')).toContainText('1 Bryant Park, New York, NY');
  await expect(page.getByTestId('ptl-chip-label-0')).toHaveValue('Office');
  await expect(page.getByTestId('ptl-chip-1')).toContainText('320 E 46th St, New York, NY');
  await expect(page.getByTestId('ptl-chip-label-1')).toHaveValue('Home');

  await expect(page.getByTestId('pps-chip-0')).toContainText('New York Public Library');
  await expect(page.getByTestId('pps-chip-1')).toContainText('Times Square');
});
