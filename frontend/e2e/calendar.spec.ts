import { test, expect, type Page } from '@playwright/test';
import { seedSessionCookie } from './support/cookies';
import { isInstructor } from './utils/projects';

test.beforeAll(({}, workerInfo) => {
  test.skip(!isInstructor(workerInfo), `Instructor-only spec (current project: ${workerInfo.project.name})`);
});

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3100';
const SESSION_TOKEN = process.env.TEST_SESSION_TOKEN ?? 'fake.jwt.value';
const SESSION_COOKIE_NAME = process.env.SESSION_COOKIE_NAME;

type ScheduleEntry = { date: string; start_time: string; end_time: string };
type ScheduleSeed = Record<string, Array<Omit<ScheduleEntry, 'date'>>>;

type WeekContext = {
  dates: {
    base: Date;
    next: Date;
    later: Date;
    weekEnd: Date;
  };
  iso: {
    base: string;
    next: string;
    later: string;
    weekEnd: string;
  };
};

const formatISODate = (date: Date): string => {
  const [day] = date.toISOString().split('T');
  if (!day) {
    throw new Error('Unable to derive ISO date from timestamp');
  }
  return day;
};

const addDays = (date: Date, days: number) => {
  const next = new Date(date);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
};

const createWeekContext = (): WeekContext => {
  const now = new Date();
  const base = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  const offset = (8 - base.getUTCDay()) % 7;
  base.setUTCDate(base.getUTCDate() + offset);
  base.setUTCHours(0, 0, 0, 0);
  const next = addDays(base, 1);
  const later = addDays(base, 3);
  const weekEnd = addDays(base, 6);
  return {
    dates: { base, next, later, weekEnd },
    iso: {
      base: formatISODate(base),
      next: formatISODate(next),
      later: formatISODate(later),
      weekEnd: formatISODate(weekEnd),
    },
  };
};

const createInitialSchedule = (iso: WeekContext['iso']): ScheduleSeed => ({
  [iso.base]: [
    { start_time: '08:00:00', end_time: '10:00:00' },
    { start_time: '23:30:00', end_time: '01:00:00' },
  ],
  [iso.next]: [
    { start_time: '00:00:00', end_time: '02:00:00' },
    { start_time: '14:00:00', end_time: '18:00:00' },
  ],
});

const createBookedSlots = (iso: WeekContext['iso']) => [
  {
    booking_id: 'BOOK1',
    date: iso.next,
    start_time: '14:00:00',
    end_time: '14:30:00',
    student_first_name: 'Alex',
    student_last_initial: 'R',
    service_name: 'Lesson',
    service_area_short: 'NYC',
    duration_minutes: 30,
    location_type: 'student_home',
  },
];

const buildAvailabilityRows = (schedule: ScheduleSeed) =>
  Object.entries(schedule).flatMap(([date, slots]) =>
    slots.map((slot, idx) => ({
      id: `${date}-${slot.start_time}-${idx}`,
      specific_date: date,
      start_time: slot.start_time,
      end_time: slot.end_time,
    }))
  );

const fulfillJson = async (
  route: import('@playwright/test').Route,
  body: unknown,
  status = 200,
  headers: Record<string, string> = {}
) => {
  await route.fulfill({ status, contentType: 'application/json', headers, body: JSON.stringify(body) });
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

const setupInstructorSession = async (page: Page) => {
  await seedSessionCookie(page.context(), BASE_URL, SESSION_TOKEN, SESSION_COOKIE_NAME);
  await stubAuthMe(page);
  await stubInstructorProfile(page);
};

const alignCalendarToWeek = async (page: Page, mondayISO: string) => {
  const header = page.getByTestId('week-header');
  await expect(header).toBeVisible();

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

const availabilityCell = (page: Page, dateISO: string, time: string) =>
  page.locator(`[data-testid="availability-cell"][data-date="${dateISO}"][data-time="${time}"]`);

const weekdayShort = (date: Date) => date.toLocaleDateString('en-US', { weekday: 'short', timeZone: 'UTC' });

const waitForWeekResponse = (page: Page, method: 'GET' | 'POST', weekStart?: string) =>
  page.waitForResponse((response) => {
    const url = response.url();
    if (!url.includes('/api/v1/instructors/availability/week')) {
      return false;
    }
    if (response.request().method() !== method) {
      return false;
    }
    if (weekStart) {
      const encodedWeekStart = encodeURIComponent(weekStart);
      const hasWeekParam = url.includes('week_start=');
      if (hasWeekParam) {
        const matchesWeek =
          url.includes(`week_start=${weekStart}`) || url.includes(`week_start=${encodedWeekStart}`);
        if (!matchesWeek) {
          return false;
        }
      }
    }
    if (method === 'GET' && response.status() !== 200) {
      return false;
    }
    return true;
  });

test.describe('Instructor availability calendar', () => {
  test.describe.configure({ mode: 'serial' });
  test.beforeEach(async ({ page }) => {
    await setupInstructorSession(page);
  });
  test('persists past edits with ETag handshake', async ({ page }) => {
    const week = createWeekContext();
    const initialSchedule = createInitialSchedule(week.iso);
    const bookedSlots = createBookedSlots(week.iso);

    let currentSchedule = structuredClone(initialSchedule);
    let currentEtag = '"v1"';
    const postedSchedules: ScheduleEntry[][] = [];
    const ifMatchHeaders: Array<string | undefined> = [];
    const baseVersions: Array<string | undefined> = [];

    await page.route(/.*\/instructors\/availability(\?.*)?$/, (route) =>
      fulfillJson(route, buildAvailabilityRows(currentSchedule))
    );

    await page.route(/.*\/instructors\/availability\/week\/booked-slots(\?.*)?$/, (route, request) =>
      request.method() === 'GET' ? fulfillJson(route, { booked_slots: bookedSlots }) : route.fallback()
    );

    await page.route(/.*\/instructors\/availability\/week(\?.*)?$/, async (route, request) => {
      if (request.method() === 'GET') {
        await fulfillJson(route, currentSchedule, 200, { ETag: currentEtag });
        await page.evaluate(
          (version) => {
            (window as Window & { __week_version?: string }).__week_version = version;
          },
          currentEtag
        );
        return;
      }

      if (request.method() === 'POST') {
        const payload = (await request.postDataJSON()) as {
          schedule?: ScheduleEntry[];
          override?: boolean;
          base_version?: string | null;
        };
        const schedulePayload = payload?.schedule ?? [];
        const headers = await request.allHeaders();
        const ifMatchValue = headers['if-match'] ?? headers['If-Match'] ?? headers['IF-MATCH'];
    ifMatchHeaders.push(ifMatchValue ?? undefined);
        baseVersions.push(payload.base_version ?? undefined);
        expect(payload.override ?? false).toBe(false);
        expect(ifMatchValue).toBe(currentEtag);
        const grouped: typeof currentSchedule = {};
        for (const entry of schedulePayload) {
          const targetDate = entry.date;
          grouped[targetDate] = grouped[targetDate] || [];
          grouped[targetDate]!.push({ start_time: entry.start_time, end_time: entry.end_time });
        }
        postedSchedules.push(schedulePayload);
        currentSchedule = grouped;
        currentEtag = '"v2"';
        await fulfillJson(
          route,
          {
            message: 'Saved weekly availability',
            week_start: week.iso.base,
            week_end: week.iso.weekEnd,
            windows_created: schedulePayload.length,
            windows_updated: 0,
            windows_deleted: 0,
            version: currentEtag,
          },
          200,
          { ETag: currentEtag }
        );
        await page.evaluate(
          (version) => {
            (window as Window & { __week_version?: string }).__week_version = version;
          },
          currentEtag
        );
        return;
      }

      await route.fallback();
    });

    const initialWeekResponsePromise = waitForWeekResponse(page, 'GET', week.iso.base);
    await page.goto('/instructor/dashboard?panel=availability');
    await alignCalendarToWeek(page, week.iso.base);
    const initialWeekResponse = await initialWeekResponsePromise;
    const initialEtag = initialWeekResponse.headers()['etag'];
    expect(initialEtag).toBeTruthy();
    await page.evaluate(
      (version) => {
        (window as Window & { __week_version?: string }).__week_version = version;
      },
      currentEtag
    );
    const addPastSlotStart = availabilityCell(page, week.iso.base, '13:00:00');
    const addPastSlotEnd = availabilityCell(page, week.iso.base, '14:00:00');
    await addPastSlotStart.scrollIntoViewIfNeeded();
    await expect(addPastSlotStart).toBeVisible();
    await addPastSlotEnd.scrollIntoViewIfNeeded();
    await expect(addPastSlotEnd).toBeVisible();
    await addPastSlotStart.click();
    await addPastSlotEnd.click();
    await expect(addPastSlotEnd).toHaveAttribute('aria-selected', 'true');

    const addFutureSlotStart = availabilityCell(page, week.iso.later, '15:00:00');
    const addFutureSlotEnd = availabilityCell(page, week.iso.later, '16:00:00');
    await addFutureSlotStart.scrollIntoViewIfNeeded();
    await expect(addFutureSlotStart).toBeVisible();
    await addFutureSlotEnd.scrollIntoViewIfNeeded();
    await expect(addFutureSlotEnd).toBeVisible();
    await addFutureSlotStart.click();
    await addFutureSlotEnd.click();
    await expect(addFutureSlotEnd).toHaveAttribute('aria-selected', 'true');

    const bookedSlotStart = availabilityCell(page, week.iso.next, '14:00:00');
    const bookedSlotEnd = availabilityCell(page, week.iso.next, '15:00:00');
    await bookedSlotStart.scrollIntoViewIfNeeded();
    await expect(bookedSlotStart).toBeVisible();
    await bookedSlotEnd.scrollIntoViewIfNeeded();
    await expect(bookedSlotEnd).toHaveAttribute('aria-selected', 'true');

    const nextDayAdditionalStart = availabilityCell(page, week.iso.next, '09:00:00');
    const nextDayAdditionalEnd = availabilityCell(page, week.iso.next, '10:00:00');
    await nextDayAdditionalStart.scrollIntoViewIfNeeded();
    await expect(nextDayAdditionalStart).toBeVisible();
    await nextDayAdditionalEnd.scrollIntoViewIfNeeded();
    await expect(nextDayAdditionalEnd).toBeVisible();
    await nextDayAdditionalStart.click();
    await nextDayAdditionalEnd.click();
    await expect(nextDayAdditionalEnd).toHaveAttribute('aria-selected', 'true');

    await expect(page.getByText('Unsaved changes')).toBeVisible();

    const postResponsePromise = waitForWeekResponse(page, 'POST', week.iso.base);
    await page.getByRole('button', { name: 'Save Week' }).click();
    const postResponse = await postResponsePromise;
    const postStatus = postResponse.status();
    expect([200, 409]).toContain(postStatus);
    const postEtag = postResponse.headers()['etag'];
    expect(postEtag).toBeTruthy();
    await expect(page.getByText('Unsaved changes')).toBeHidden();

    const followupWeekResponsePromise = waitForWeekResponse(page, 'GET', week.iso.base);
    if (postStatus === 409) {
      await page.getByTestId('conflict-refresh').click();
      await alignCalendarToWeek(page, week.iso.base);
    } else {
      await page.reload({ waitUntil: 'domcontentloaded' });
      await alignCalendarToWeek(page, week.iso.base);
    }
    const followupWeekResponse = await followupWeekResponsePromise;
    const refreshedEtag = followupWeekResponse.headers()['etag'];
    expect(refreshedEtag).toBeTruthy();
    expect(refreshedEtag).not.toBe(initialEtag);

    expect(ifMatchHeaders).toEqual(['"v1"']);
    expect(baseVersions).toEqual(['"v1"']);

    const scheduleEntries = postedSchedules.at(-1);
    expect(scheduleEntries).toBeDefined();
    if (!scheduleEntries) {
      throw new Error('Missing posted schedule payload');
    }
    expect(scheduleEntries).toEqual(
      expect.arrayContaining([
        { date: week.iso.base, start_time: '13:00:00', end_time: '13:30:00' },
        { date: week.iso.base, start_time: '14:00:00', end_time: '14:30:00' },
        { date: week.iso.later, start_time: '15:00:00', end_time: '15:30:00' },
        { date: week.iso.later, start_time: '16:00:00', end_time: '16:30:00' },
        { date: week.iso.next, start_time: '09:00:00', end_time: '09:30:00' },
        { date: week.iso.next, start_time: '10:00:00', end_time: '10:30:00' },
      ])
    );
  });

  test('conflict modal supports refresh and overwrite flows', async ({ page }) => {
    const week = createWeekContext();
    const initialSchedule = createInitialSchedule(week.iso);
    const bookedSlots = createBookedSlots(week.iso);

    let currentSchedule = structuredClone(initialSchedule);
    let currentEtag = '"v1"';
    let conflictCounter = 0;
    const postedSchedules: ScheduleEntry[][] = [];
    const ifMatchHeaders: Array<string | undefined> = [];
    const baseVersions: Array<string | undefined> = [];

    await page.route(/.*\/instructors\/availability(\?.*)?$/, (route) =>
      fulfillJson(route, buildAvailabilityRows(currentSchedule))
    );

    await page.route(/.*\/instructors\/availability\/week\/booked-slots(\?.*)?$/, (route, request) =>
      request.method() === 'GET' ? fulfillJson(route, { booked_slots: bookedSlots }) : route.fallback()
    );

    await page.route(/.*\/instructors\/availability\/week(\?.*)?$/, async (route, request) => {
      if (request.method() === 'GET') {
        await fulfillJson(route, currentSchedule, 200, { ETag: currentEtag });
        await page.evaluate(
          (version) => {
            (window as Window & { __week_version?: string }).__week_version = version;
          },
          currentEtag
        );
        return;
      }

      if (request.method() === 'POST') {
        const payload = (await request.postDataJSON()) as {
          schedule?: ScheduleEntry[];
          override?: boolean;
          base_version?: string | null;
        };
        const headers = await request.allHeaders();
        const ifMatchValue = headers['if-match'] ?? headers['If-Match'] ?? headers['IF-MATCH'];
        ifMatchHeaders.push(ifMatchValue ?? undefined);
        baseVersions.push(payload.base_version ?? undefined);
        const schedulePayload = payload?.schedule ?? [];
        if (!payload.override) {
          expect(ifMatchValue).toBe(currentEtag);
          conflictCounter += 1;
          const conflictVersion = conflictCounter === 1 ? '"v2"' : '"v3"';
          currentEtag = conflictVersion;
          await fulfillJson(route, { error: 'version_conflict', current_version: conflictVersion }, 409, {
            ETag: conflictVersion,
          });
          await page.evaluate(
            (version) => {
              (window as Window & { __week_version?: string }).__week_version = version;
            },
            conflictVersion
          );
          return;
        }
        expect(ifMatchValue).toBe(currentEtag);
        const grouped: typeof currentSchedule = {};
        for (const entry of schedulePayload) {
          const targetDate = entry.date;
          grouped[targetDate] = grouped[targetDate] || [];
          grouped[targetDate]!.push({ start_time: entry.start_time, end_time: entry.end_time });
        }
        postedSchedules.push(schedulePayload);
        currentSchedule = grouped;
        currentEtag = '"v4"';
        await fulfillJson(
          route,
          {
            message: 'Saved weekly availability',
            week_start: week.iso.base,
            week_end: week.iso.weekEnd,
            windows_created: schedulePayload.length,
            windows_updated: 0,
            windows_deleted: 0,
            version: currentEtag,
          },
          200,
          { ETag: currentEtag }
        );
        await page.evaluate(
          (version) => {
            (window as Window & { __week_version?: string }).__week_version = version;
          },
          currentEtag
        );
        return;
      }

      await route.fallback();
    });

    await page.goto('/instructor/dashboard?panel=availability');
    await alignCalendarToWeek(page, week.iso.base);
    await page.evaluate(
      (version) => {
        (window as Window & { __week_version?: string }).__week_version = version;
      },
      currentEtag
    );

    const targetCell = availabilityCell(page, week.iso.base, '13:00:00');
    const targetCellPair = availabilityCell(page, week.iso.base, '14:00:00');
    await targetCell.scrollIntoViewIfNeeded();
    await expect(targetCell).toBeVisible();
    await targetCellPair.scrollIntoViewIfNeeded();
    await expect(targetCellPair).toBeVisible();
    await targetCell.click();
    await targetCellPair.click();
    await expect(targetCellPair).toHaveAttribute('aria-selected', 'true');

    const firstPostPromise = waitForWeekResponse(page, 'POST');
    await page.getByRole('button', { name: 'Save Week' }).click();
    const firstPost = await firstPostPromise;
    expect(firstPost.status()).toBe(409);
    expect(firstPost.headers()['etag']).toBe(currentEtag);

    const conflictModal = page.getByRole('dialog');
    await expect(conflictModal).toBeVisible();
    await expect(page.getByText('Latest version: "v2"')).toBeVisible();

    await page.getByRole('button', { name: 'Refresh' }).click();
    await alignCalendarToWeek(page, week.iso.base);
    await expect(conflictModal).toBeHidden();
    await expect(targetCellPair).toHaveAttribute('aria-selected', 'false');
    await page.evaluate(
      (version) => {
        (window as Window & { __week_version?: string }).__week_version = version;
      },
      currentEtag
    );

    await targetCell.click();
    await targetCellPair.click();
    await expect(targetCellPair).toHaveAttribute('aria-selected', 'true');
    const secondPostPromise = waitForWeekResponse(page, 'POST');
    await page.getByRole('button', { name: 'Save Week' }).click();
    const secondPost = await secondPostPromise;
    expect(secondPost.status()).toBe(409);
    expect(secondPost.headers()['etag']).toBe(currentEtag);

    const conflictModalSecond = page.getByRole('dialog');
    await expect(conflictModalSecond).toBeVisible();
    await expect(page.getByText('Latest version: "v3"')).toBeVisible();
    await page.evaluate(
      (version) => {
        (window as Window & { __week_version?: string }).__week_version = version;
      },
      currentEtag
    );

    const overridePostPromise = waitForWeekResponse(page, 'POST');
    await page.getByRole('button', { name: 'Overwrite' }).click();
    const overridePost = await overridePostPromise;
    expect(overridePost.status()).toBe(200);
    expect(overridePost.headers()['etag']).toBe(currentEtag);
    await expect(conflictModalSecond).toBeHidden();
    await expect(page.getByText('Unsaved changes')).toBeHidden();

    expect(conflictCounter).toBe(2);
    expect(ifMatchHeaders).toEqual(['"v1"', '"v2"', '"v3"']);
    expect(baseVersions).toEqual(['"v1"', '"v2"', '"v3"']);
    const finalSchedule = postedSchedules.at(-1);
    expect(finalSchedule).toBeDefined();
    if (!finalSchedule) {
      throw new Error('Missing final posted schedule payload');
    }
    expect(finalSchedule).toEqual(
      expect.arrayContaining([
        { date: week.iso.base, start_time: '13:00:00', end_time: '13:30:00' },
        { date: week.iso.base, start_time: '14:00:00', end_time: '14:30:00' },
      ])
    );
  });

  test('mobile layout renders day chips', async ({ page }) => {
    const week = createWeekContext();
    const initialSchedule = createInitialSchedule(week.iso);

    await page.setViewportSize({ width: 375, height: 812 });

    await page.route(/.*\/instructors\/availability(\?.*)?$/, (route) =>
      fulfillJson(route, buildAvailabilityRows(initialSchedule))
    );

    await page.route(/.*\/instructors\/availability\/week(\?.*)?$/, (route, request) =>
      request.method() === 'GET'
        ? fulfillJson(route, initialSchedule, 200, { ETag: '"v1"' })
        : route.fallback()
    );

    await page.route(/.*\/instructors\/availability\/week\/booked-slots(\?.*)?$/, (route, request) =>
      request.method() === 'GET' ? fulfillJson(route, { booked_slots: [] }) : route.fallback()
    );

    const mobileWeekResponse = waitForWeekResponse(page, 'GET');
    await page.goto('/instructor/dashboard?panel=availability');
    await mobileWeekResponse;
    await alignCalendarToWeek(page, week.iso.base);

    const chipLabel = weekdayShort(week.dates.base);
    const chipList = page.getByRole('button', { name: chipLabel });
    await expect(chipList.first()).toBeVisible();
    const morningCell = availabilityCell(page, week.iso.base, '08:00:00');
    await morningCell.scrollIntoViewIfNeeded();
    await expect(morningCell).toBeVisible();
  });
});
