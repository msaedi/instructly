import { test, expect, type Page } from '@playwright/test';
import { isInstructor } from '../utils/projects';
import { seedSessionCookie } from '../support/cookies';
import { mockAuthenticatedPageBackgroundApis } from '../utils/authenticatedPageMocks';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isInstructor(workerInfo), `Instructor-only spec (current project: ${workerInfo.project.name})`);
});

test.describe.configure({ mode: 'serial' });

type ScheduleEntry = { date: string; start_time: string; end_time: string };
type ScheduleSeed = Record<string, Array<Omit<ScheduleEntry, 'date'>>>;

type WeekContext = {
  iso: {
    base: string;
    next: string;
  };
};

type RouteState = {
  schedule: ScheduleSeed;
  etag: string;
  version: number;
};

const formatISODate = (date: Date) => {
  const [day] = date.toISOString().split('T');
  if (!day) {
    throw new Error('Unable to derive ISO date from timestamp');
  }
  return day;
};

const createWeekContext = (): WeekContext => {
  const now = new Date();
  const base = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const offset = ((8 - base.getUTCDay()) % 7) || 7;
  base.setUTCDate(base.getUTCDate() + offset);
  base.setUTCHours(0, 0, 0, 0);
  const next = new Date(base);
  next.setUTCDate(base.getUTCDate() + 1);
  return {
    iso: {
      base: formatISODate(base),
      next: formatISODate(next),
    },
  };
};

const buildAvailabilityRows = (schedule: ScheduleSeed) =>
  Object.entries(schedule).flatMap(([date, slots]) =>
    slots.map((slot, idx) => ({
      id: `${date}-${slot.start_time}-${idx}`,
      specific_date: date,
      start_time: slot.start_time,
      end_time: slot.end_time,
    }))
  );

const groupSchedule = (entries: ScheduleEntry[]) => {
  const grouped: ScheduleSeed = {};
  for (const entry of entries) {
    grouped[entry.date] = grouped[entry.date] || [];
    grouped[entry.date]!.push({ start_time: entry.start_time, end_time: entry.end_time });
  }
  return grouped;
};

const availabilityCell = (page: Page, dateISO: string, time: string) =>
  page.locator(`[data-testid="availability-cell"][data-date="${dateISO}"][data-time="${time}"]`);

const alignCalendarToWeek = async (page: Page, mondayISO: string) => {
  const header = page.getByTestId('week-header').first();
  await page.waitForLoadState('domcontentloaded');
  try {
    await header.waitFor({ state: 'visible', timeout: 15_000 });
  } catch {
    await page
      .getByRole('heading', { name: /availability/i })
      .waitFor({ state: 'visible', timeout: 15_000 })
      .catch(() => undefined);
    await page.waitForTimeout(200);
    await header.waitFor({ state: 'visible', timeout: 15_000 });
  }

  for (let attempt = 0; attempt < 8; attempt += 1) {
    const currentWeek = await header.getAttribute('data-week-start');
    if (currentWeek === mondayISO) {
      await expect(header).toHaveAttribute('data-week-start', mondayISO);
      return;
    }

    if (!currentWeek) {
      await page.waitForTimeout(50);
      continue;
    }

    const buttonName = currentWeek < mondayISO ? /next week/i : /previous week/i;
    await page.getByRole('button', { name: buttonName }).click();
    await page.waitForTimeout(50);
  }

  await expect(header).toHaveAttribute('data-week-start', mondayISO);
};

const STORAGE_STATE_PATH = process.env.PLAYWRIGHT_STORAGE_STATE || 'e2e/.storage/instructor.json';
const SESSION_TOKEN = process.env.TEST_SESSION_TOKEN ?? 'fake.jwt.value';
const SESSION_COOKIE_NAME = process.env.SESSION_COOKIE_NAME;

const setClientVersionOnPage = async (page: Page, version: string) => {
  await page.evaluate((etag) => {
    (window as Window & { __week_version?: string }).__week_version = etag;
  }, version);
};

const stubAuthMe = async (page: Page) => {
  await page.route('**/api/v1/auth/me', async (route, request) => {
    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'instructor-1',
          first_name: 'Test',
          last_name: 'Instructor',
          roles: ['instructor'],
        }),
      });
      return;
    }
    await route.continue();
  });
};

const stubInstructorProfile = async (page: Page) => {
  const profilePayload = {
    id: 'instructor-profile',
    bio: 'Experienced instructor ready to teach.',
    service_area_summary: 'Manhattan',
    service_area_boroughs: ['Manhattan'],
    service_area_neighborhoods: [
      {
        neighborhood_id: 'MN01',
        name: 'Central Village',
        borough: 'Manhattan',
        ntacode: 'MN01',
      },
    ],
    years_experience: 5,
    min_advance_booking_hours: 2,
    buffer_time_minutes: 15,
    preferred_teaching_locations: [],
    preferred_public_spaces: [],
    services: [],
    user: {
      id: 'mock-user',
      first_name: 'Test',
      last_name: 'Instructor',
      zip_code: '10001',
      roles: ['instructor'],
    },
    is_live: true,
  };
  await page.route('**/instructors/me', async (route, request) => {
    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profilePayload),
      });
      return;
    }
    if (request.method() === 'PUT' || request.method() === 'PATCH') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(profilePayload),
      });
      return;
    }
    await route.continue();
  });
};
const createRouteState = (schedule: ScheduleSeed): RouteState => ({
  schedule,
  etag: '"v1"',
  version: 1,
});

const setClientVersion = async (page: Page, version: string | null) => {
  try {
    await page.evaluate(
      (v) => {
        const win = window as Window & { __week_version?: string };
        if (v) {
          win.__week_version = v;
        } else {
          delete win.__week_version;
        }
      },
      version
    );
  } catch {
    // ignore if page not ready yet
  }
};

const setupAvailabilityRoutes = async (page: Page, state: RouteState) => {
  await page.route(/.*\/instructors\/availability(\?.*)?$/, async (route, request) => {
    if (request.method() !== 'GET') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(buildAvailabilityRows(state.schedule)),
    });
  });

  await page.route(/.*\/instructors\/availability\/week\/booked-slots(\?.*)?$/, async (route, request) => {
    if (request.method() === 'GET') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ booked_slots: [] }) });
      return;
    }
    await route.fallback();
  });

  await page.route(/.*\/instructors\/availability\/week(\?.*)?$/, async (route, request) => {
    if (request.method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: {
          ETag: state.etag,
          'Last-Modified': new Date().toUTCString(),
        },
        body: JSON.stringify(state.schedule),
      });
      await setClientVersion(page, state.etag);
      return;
    }

    if (request.method() === 'POST') {
      const payload = (await request.postDataJSON()) as { schedule?: ScheduleEntry[]; override?: boolean };
      const headers = await request.allHeaders();
      const ifMatch = headers['if-match'] ?? headers['If-Match'] ?? headers['IF-MATCH'];
      const override = Boolean(payload.override);

      if (!override && ifMatch !== state.etag) {
        await route.fulfill({
          status: 409,
          contentType: 'application/json',
          headers: { ETag: state.etag },
          body: JSON.stringify({ error: 'version_conflict', current_version: state.etag }),
        });
        await setClientVersion(page, state.etag);
        return;
      }

      state.schedule = groupSchedule(payload.schedule ?? []);
      state.version += 1;
      state.etag = `"v${state.version}"`;

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        headers: { ETag: state.etag, 'Last-Modified': new Date().toUTCString() },
        body: JSON.stringify({
          message: 'Saved weekly availability',
          week_start: Object.keys(state.schedule)[0] ?? '',
          week_end: Object.keys(state.schedule)[0] ?? '',
          windows_created: payload.schedule?.length ?? 0,
          windows_updated: 0,
          windows_deleted: 0,
        }),
      });
      await setClientVersion(page, state.etag);
      return;
    }

    await route.fallback();
  });
};

const selectCells = async (page: Page, dateISO: string, times: string[]) => {
  for (const time of times) {
    const cell = availabilityCell(page, dateISO, time);
    await cell.scrollIntoViewIfNeeded();
    await expect(cell).toBeVisible();
    await cell.click();
  }
};

const saveWeek = async (page: Page) => {
  const saveButton = page.getByRole('button', { name: /save week/i });
  await saveButton.scrollIntoViewIfNeeded();
  const responsePromise = page.waitForResponse(
    (res) => res.url().includes('/api/v1/instructors/availability/week') && res.request().method() === 'POST'
  );
  await saveButton.click();
  const response = await responsePromise;
  return response;
};

const refreshWeek = async (page: Page, mondayISO: string) => {
  const refreshPromise = page.waitForResponse((res) => {
    if (!res.url().includes('/api/v1/instructors/availability/week')) {
      return false;
    }
    if (res.request().method() !== 'GET') {
      return false;
    }
    try {
      const url = new URL(res.url());
      const weekStart = url.searchParams.get('start_date') ?? url.searchParams.get('week_start');
      return weekStart === mondayISO;
    } catch {
      return false;
    }
  });
  await page.getByTestId('conflict-refresh').click();
  await refreshPromise;
  await alignCalendarToWeek(page, mondayISO);
};

test.describe('Availability 409 conflict flow', () => {

  test('shows friendly modal and refreshes on confirm', async ({ browser }) => {
    const week = createWeekContext();
    const state = createRouteState({});
    const baseURL =
      test.info().project.use?.baseURL || process.env.PLAYWRIGHT_BASE_URL || process.env.E2E_BASE_URL || 'http://localhost:3100';
    const contextA = await browser.newContext({ storageState: STORAGE_STATE_PATH, baseURL });
    const contextB = await browser.newContext({ storageState: STORAGE_STATE_PATH, baseURL });
    await seedSessionCookie(contextA, baseURL, SESSION_TOKEN, SESSION_COOKIE_NAME);
    await seedSessionCookie(contextB, baseURL, SESSION_TOKEN, SESSION_COOKIE_NAME);
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    await mockAuthenticatedPageBackgroundApis(pageA, { userId: 'instructor-1' });
    await mockAuthenticatedPageBackgroundApis(pageB, { userId: 'instructor-1' });
    await stubAuthMe(pageA);
    await stubAuthMe(pageB);
    await stubInstructorProfile(pageA);
    await stubInstructorProfile(pageB);

    await setupAvailabilityRoutes(pageA, state);
    await setupAvailabilityRoutes(pageB, state);

    await pageA.goto('/instructor/dashboard?panel=availability');
    await pageB.goto('/instructor/dashboard?panel=availability');

    await alignCalendarToWeek(pageA, week.iso.base);
    await alignCalendarToWeek(pageB, week.iso.base);
    await setClientVersionOnPage(pageA, state.etag);
    await setClientVersionOnPage(pageB, state.etag);

    // Page A: make a change but do not save yet
    await selectCells(pageA, week.iso.base, ['13:00:00', '13:30:00']);

    // Page B: make and save a different change to bump the version
    await selectCells(pageB, week.iso.base, ['15:00:00', '15:30:00']);
    const saveResponseB = await saveWeek(pageB);
    expect(saveResponseB.status()).toBe(200);
    await expect(pageB.getByText('Unsaved changes')).toBeHidden();

    // Page A: attempt to save with stale version, expect conflict modal
    const saveResponseA = await saveWeek(pageA);
    expect(saveResponseA.status()).toBe(409);
    await expect(pageA.getByTestId('conflict-modal')).toBeVisible();

    // Refresh path should pull server version and hide modal
    await refreshWeek(pageA, week.iso.base);
    await expect(pageA.getByTestId('conflict-modal')).toBeHidden();

    const staleCell = availabilityCell(pageA, week.iso.base, '13:00:00');
    const serverCell = availabilityCell(pageA, week.iso.base, '15:00:00');
    await expect(staleCell).toHaveAttribute('aria-selected', 'false');
    await expect(serverCell).toHaveAttribute('aria-selected', 'true');

    await contextA.close();
    await contextB.close();
  });

  test('allows overwrite to force current changes', async ({ browser }) => {
    const week = createWeekContext();
    const state = createRouteState({});
    const baseURL =
      test.info().project.use?.baseURL || process.env.PLAYWRIGHT_BASE_URL || process.env.E2E_BASE_URL || 'http://localhost:3100';
    const contextA = await browser.newContext({ storageState: STORAGE_STATE_PATH, baseURL });
    const contextB = await browser.newContext({ storageState: STORAGE_STATE_PATH, baseURL });
    await seedSessionCookie(contextA, baseURL, SESSION_TOKEN, SESSION_COOKIE_NAME);
    await seedSessionCookie(contextB, baseURL, SESSION_TOKEN, SESSION_COOKIE_NAME);
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();
    await mockAuthenticatedPageBackgroundApis(pageA, { userId: 'instructor-1' });
    await mockAuthenticatedPageBackgroundApis(pageB, { userId: 'instructor-1' });
    await stubAuthMe(pageA);
    await stubAuthMe(pageB);
    await stubInstructorProfile(pageA);
    await stubInstructorProfile(pageB);

    await setupAvailabilityRoutes(pageA, state);
    await setupAvailabilityRoutes(pageB, state);

    await pageA.goto('/instructor/dashboard?panel=availability');
    await pageB.goto('/instructor/dashboard?panel=availability');

    await alignCalendarToWeek(pageA, week.iso.base);
    await alignCalendarToWeek(pageB, week.iso.base);
    await setClientVersionOnPage(pageA, state.etag);
    await setClientVersionOnPage(pageB, state.etag);

    // Page A plans an earlier slot
    await selectCells(pageA, week.iso.base, ['11:00:00', '11:30:00']);

    // Page B saves a later slot to bump version
    await selectCells(pageB, week.iso.base, ['16:00:00', '16:30:00']);
    const saveResponseB = await saveWeek(pageB);
    expect(saveResponseB.status()).toBe(200);

    // Page A tries to save and gets conflict
    const saveResponseA = await saveWeek(pageA);
    expect(saveResponseA.status()).toBe(409);
    await expect(pageA.getByTestId('conflict-modal')).toBeVisible();

    // Overwrite should push A's plan and close modal
    const overwritePromise = pageA.waitForResponse(
      (res) => res.url().includes('/api/v1/instructors/availability/week') && res.request().method() === 'POST'
    );
    await pageA.getByTestId('conflict-overwrite').click();
    const overwriteResponse = await overwritePromise;
    expect(overwriteResponse.status()).toBe(200);
    await expect(pageA.getByTestId('conflict-modal')).toBeHidden();
    await alignCalendarToWeek(pageA, week.iso.base);

    const chosenCell = availabilityCell(pageA, week.iso.base, '11:00:00');
    const overwrittenCell = availabilityCell(pageA, week.iso.base, '16:00:00');
    await expect(chosenCell).toHaveAttribute('aria-selected', 'true');
    await expect(overwrittenCell).toHaveAttribute('aria-selected', 'false');

    await contextA.close();
    await contextB.close();
  });
});
