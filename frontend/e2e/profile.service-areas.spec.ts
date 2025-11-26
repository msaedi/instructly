import { test, expect } from '@playwright/test';
import { isInstructor } from './utils/projects';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isInstructor(workerInfo), `Instructor-only spec (current project: ${workerInfo.project.name})`);
});
test.skip(Boolean(process.env.CI) && !process.env.CI_LOCAL_E2E, 'local-only smoke; opt-in via CI_LOCAL_E2E=1');

test('service areas: select two -> save -> reload -> persisted', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const neighborhoods = [
    { id: 'MN01', code: 'MN01', name: 'Central Village', borough: 'Manhattan' },
    { id: 'MN02', code: 'MN02', name: 'Hudson Heights', borough: 'Manhattan' },
    { id: 'BK01', code: 'BK01', name: 'Brooklyn Heights', borough: 'Brooklyn' },
  ];

  let serviceAreaSelections: string[] = [];

  const fulfillJson = async (route: import('@playwright/test').Route, body: unknown, status = 200) => {
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  };

  await page.route('**/instructors/me', async (route, request) => {
    if (request.method() === 'GET') {
      await fulfillJson(route, {
        bio: 'Experienced instructor ready to teach.',
        service_area_summary: 'Manhattan',
        service_area_boroughs: ['Manhattan'],
        service_area_neighborhoods: neighborhoods.map((n) => ({
          neighborhood_id: n.id,
          name: n.name,
          borough: n.borough,
          ntacode: n.code,
        })),
        years_experience: 5,
        min_advance_booking_hours: 2,
        buffer_time_minutes: 15,
        user: { roles: ['instructor'] },
      });
      return;
    }

    if (request.method() === 'PUT') {
      await fulfillJson(route, {
        bio: 'Experienced instructor ready to teach.',
        service_area_summary: 'Manhattan',
        service_area_boroughs: ['Manhattan'],
        service_area_neighborhoods: neighborhoods.map((n) => ({
          neighborhood_id: n.id,
          name: n.name,
          borough: n.borough,
          ntacode: n.code,
        })),
        years_experience: 5,
        min_advance_booking_hours: 2,
        buffer_time_minutes: 15,
      });
      return;
    }

    await route.continue();
  });

  await page.route('**/api/v1/auth/me', async (route, request) => {
    if (request.method() === 'GET') {
      await fulfillJson(route, {
        first_name: 'Test',
        last_name: 'Instructor',
        zip_code: '10001',
        roles: ['instructor'],
      });
      return;
    }

    if (request.method() === 'PATCH') {
      await fulfillJson(route, { ok: true }, 200);
      return;
    }

    await route.continue();
  });

  await page.route('**/api/v1/addresses/me', (route, request) => {
    if (request.method() === 'GET') {
      return fulfillJson(route, {
        items: [
          {
            id: 'addr-1',
            is_default: true,
            postal_code: '10001',
            street_line1: '123 Main St',
            locality: 'New York',
            administrative_area: 'NY',
            country_code: 'US',
          },
        ],
        total: 1,
      });
    }
    if (request.method() === 'POST') {
      return fulfillJson(route, { id: 'addr-1' }, 201);
    }
    return fulfillJson(route, {}, 204);
  });

  await page.route('**/api/v1/addresses/zip/is-nyc*', (route) => fulfillJson(route, { is_nyc: true }));

  await page.route('**/api/v1/addresses/service-areas/me', async (route, request) => {
    if (request.method() === 'GET') {
      const items = serviceAreaSelections.map((id) => {
        const meta = neighborhoods.find((n) => n.id === id);
        return {
          neighborhood_id: id,
          ntacode: meta?.code ?? id,
          name: meta?.name ?? id,
          borough: meta?.borough ?? 'Unknown',
        };
      });
      await fulfillJson(route, { items, total: items.length });
      return;
    }

    if (request.method() === 'PUT') {
      const data = await request.postDataJSON();
      serviceAreaSelections = Array.isArray(data?.neighborhood_ids) ? data.neighborhood_ids : [];
      const items = serviceAreaSelections.map((id) => {
        const meta = neighborhoods.find((n) => n.id === id);
        return {
          neighborhood_id: id,
          ntacode: meta?.code ?? id,
          name: meta?.name ?? id,
          borough: meta?.borough ?? 'Unknown',
        };
      });
      await fulfillJson(route, { items, total: items.length });
      return;
    }

    await fulfillJson(route, { items: [], total: 0 });
  });

  await page.route('**/api/v1/addresses/regions/neighborhoods*', (route) =>
    fulfillJson(route, {
      items: neighborhoods,
      total: neighborhoods.length,
      page: 1,
      per_page: neighborhoods.length,
    })
  );

  await page.goto('/instructor/profile');

  const serviceAreasCard = page.getByTestId('service-areas-card');
  await serviceAreasCard.waitFor();
  await serviceAreasCard.scrollIntoViewIfNeeded();
  await serviceAreasCard.click();

  await page.getByTestId('service-area-borough-manhattan').click();

  await page.getByTestId('service-area-chip-MN01').waitFor();

  await page.getByTestId('service-area-chip-MN01').click();
  await page.getByTestId('service-area-chip-MN02').click();

  const putPromise = page.waitForResponse((response) =>
    response.url().includes('/api/v1/addresses/service-areas/me') &&
    response.request().method() === 'PUT'
  );

  await page.getByRole('button', { name: /save changes/i }).click();
  const putResponse = await putPromise;
  expect(putResponse.status()).toBeLessThan(400);

  await expect(page.getByText('Profile saved')).toBeVisible();
  await expect(page.getByText('Profile saved')).toBeHidden();

  await page.goto('/instructor/profile');
  await page.waitForURL('**/instructor/profile**');

  const serviceAreasCardReload = page.getByTestId('service-areas-card');
  await serviceAreasCardReload.scrollIntoViewIfNeeded();
  await serviceAreasCardReload.click();
  await page.getByTestId('service-area-borough-manhattan').click();
  await page.getByTestId('service-area-chip-MN01').waitFor();

  expect(serviceAreaSelections).toEqual(['MN01', 'MN02']);

  await page.reload();

  const serviceAreasCardReloadSecond = page.getByTestId('service-areas-card');
  await serviceAreasCardReloadSecond.scrollIntoViewIfNeeded();
  await serviceAreasCardReloadSecond.click();
  await page.getByTestId('service-area-borough-manhattan').click();
  await page.getByTestId('service-area-chip-MN01').waitFor();

  await expect(page.getByTestId('service-area-chip-MN01')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('service-area-chip-MN02')).toHaveAttribute('aria-pressed', 'true');
});
