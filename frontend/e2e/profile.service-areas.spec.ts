import { test, expect } from '@playwright/test';
import { isInstructor } from './utils/projects';
import { mockAuthenticatedPageBackgroundApis } from './utils/authenticatedPageMocks';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isInstructor(workerInfo), `Instructor-only spec (current project: ${workerInfo.project.name})`);
});
test.skip(Boolean(process.env.CI) && !process.env['CI_LOCAL_E2E'], 'local-only smoke; opt-in via CI_LOCAL_E2E=1');

test('service areas: select two -> save -> reload -> persisted', async ({ page }) => {
  await mockAuthenticatedPageBackgroundApis(page, { userId: 'mock-user' });
  await page.setViewportSize({ width: 1440, height: 900 });
  const neighborhoods = [
    { display_key: 'mn-central-village', nta_id: 'MN01', name: 'Central Village', borough: 'Manhattan' },
    { display_key: 'mn-hudson-heights', nta_id: 'MN02', name: 'Hudson Heights', borough: 'Manhattan' },
    { display_key: 'bk-brooklyn-heights', nta_id: 'BK01', name: 'Brooklyn Heights', borough: 'Brooklyn' },
  ];

  let serviceAreaSelections: string[] = [];

  const fulfillJson = async (route: import('@playwright/test').Route, body: unknown, status = 200) => {
    await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
  };

  const selectorResponse = {
    market: 'nyc',
    boroughs: [
      {
        borough: 'Manhattan',
        items: neighborhoods
          .filter((item) => item.borough === 'Manhattan')
          .map((item, index) => ({
            borough: item.borough,
            display_key: item.display_key,
            display_name: item.name,
            display_order: index + 1,
            nta_ids: [item.nta_id],
            search_terms: [
              { term: item.name, type: 'display_name' },
            ],
            additional_boroughs: [],
          })),
      },
      {
        borough: 'Brooklyn',
        items: neighborhoods
          .filter((item) => item.borough === 'Brooklyn')
          .map((item, index) => ({
            borough: item.borough,
            display_key: item.display_key,
            display_name: item.name,
            display_order: index + 1,
            nta_ids: [item.nta_id],
            search_terms: [
              { term: item.name, type: 'display_name' },
            ],
            additional_boroughs: [],
          })),
      },
    ],
    total_items: neighborhoods.length,
  };

  const polygonResponse = {
    type: 'FeatureCollection',
    features: neighborhoods.map((item, index) => {
      const x = -74.05 + index * 0.02;
      const y = 40.68 + index * 0.02;
      return {
        type: 'Feature',
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [x, y],
            [x + 0.01, y],
            [x + 0.01, y + 0.01],
            [x, y + 0.01],
            [x, y],
          ]],
        },
        properties: {
          id: item.nta_id,
          display_key: item.display_key,
          display_name: item.name,
          borough: item.borough,
          region_name: item.name,
        },
      };
    }),
  };

  await page.route('**/instructors/me', async (route, request) => {
    if (request.method() === 'GET') {
      await fulfillJson(route, {
        bio: 'Experienced instructor ready to teach.',
        service_area_summary: 'Manhattan',
        service_area_boroughs: ['Manhattan'],
        service_area_neighborhoods: neighborhoods.map((n) => ({
          display_key: n.display_key,
          display_name: n.name,
          borough: n.borough,
        })),
        years_experience: 5,
        non_travel_buffer_minutes: 15,
        travel_buffer_minutes: 60,
        overnight_protection_enabled: true,
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
          display_key: n.display_key,
          display_name: n.name,
          borough: n.borough,
        })),
        years_experience: 5,
        non_travel_buffer_minutes: 15,
        travel_buffer_minutes: 60,
        overnight_protection_enabled: true,
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
      const items = serviceAreaSelections.map((key) => {
        const meta = neighborhoods.find((n) => n.display_key === key);
        return {
          display_key: key,
          display_name: meta?.name ?? key,
          borough: meta?.borough ?? 'Unknown',
        };
      });
      await fulfillJson(route, { items, total: items.length });
      return;
    }

    if (request.method() === 'PUT') {
      const data = await request.postDataJSON();
      serviceAreaSelections = Array.isArray(data?.display_keys) ? data.display_keys : [];
      const items = serviceAreaSelections.map((key) => {
        const meta = neighborhoods.find((n) => n.display_key === key);
        return {
          display_key: key,
          display_name: meta?.name ?? key,
          borough: meta?.borough ?? 'Unknown',
        };
      });
      await fulfillJson(route, { items, total: items.length });
      return;
    }

    await fulfillJson(route, { items: [], total: 0 });
  });

  await page.route('**/api/v1/addresses/neighborhoods/selector*', (route) =>
    fulfillJson(route, selectorResponse)
  );

  await page.route('**/api/v1/addresses/neighborhoods/polygons*', (route) =>
    fulfillJson(route, polygonResponse)
  );

  await page.goto('/instructor/profile');
  const serviceAreasToggle = page.getByRole('button', { name: /service areas/i });
  await serviceAreasToggle.click();

  const serviceAreasCard = page.getByTestId('neighborhood-selector');
  await serviceAreasCard.waitFor();
  await serviceAreasCard.scrollIntoViewIfNeeded();

  await page.getByTestId('neighborhood-chip-mn-central-village').waitFor();

  await page.getByTestId('neighborhood-chip-mn-central-village').click();
  await page.getByTestId('neighborhood-chip-mn-hudson-heights').click();

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
  await serviceAreasToggle.click();

  const serviceAreasCardReload = page.getByTestId('neighborhood-selector');
  await serviceAreasCardReload.scrollIntoViewIfNeeded();
  await page.getByTestId('neighborhood-chip-mn-central-village').waitFor();

  expect(serviceAreaSelections).toEqual(['mn-central-village', 'mn-hudson-heights']);

  await page.reload();
  await serviceAreasToggle.click();

  const serviceAreasCardReloadSecond = page.getByTestId('neighborhood-selector');
  await serviceAreasCardReloadSecond.scrollIntoViewIfNeeded();
  await page.getByTestId('neighborhood-chip-mn-central-village').waitFor();

  await expect(page.getByTestId('neighborhood-chip-mn-central-village')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByTestId('neighborhood-chip-mn-hudson-heights')).toHaveAttribute('aria-pressed', 'true');
});
