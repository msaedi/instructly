import { test, expect } from '@playwright/test';

type ScheduleEntry = { date: string; start_time: string; end_time: string };
type ScheduleSeed = Record<string, Array<Omit<ScheduleEntry, 'date'>>>;

const initialSchedule: ScheduleSeed = {
  '2025-05-05': [
    { start_time: '08:00:00', end_time: '10:00:00' },
    { start_time: '23:30:00', end_time: '01:00:00' },
  ],
  '2025-05-06': [
    { start_time: '00:00:00', end_time: '02:00:00' },
    { start_time: '14:00:00', end_time: '18:00:00' },
  ],
};

const bookedSlots = [
  {
    booking_id: 'BOOK1',
    date: '2025-05-06',
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

const freezeDateScript = ({ fixedNow }: { fixedNow: string }) => {
  const now = new Date(fixedNow).valueOf();
  const OriginalDate = Date;
  class MockDate extends OriginalDate {
    constructor(...args: unknown[]) {
      if (args.length === 0) {
        super(now);
      } else {
        super(...(args as ConstructorParameters<typeof OriginalDate>));
      }
    }
    static now() {
      return now;
    }
  }
  MockDate.parse = OriginalDate.parse;
  MockDate.UTC = OriginalDate.UTC;
  Object.setPrototypeOf(MockDate, OriginalDate);
  (window as unknown as { Date: typeof Date }).Date = MockDate as unknown as typeof Date;
};

const fulfillJson = async (
  route: import('@playwright/test').Route,
  body: unknown,
  status = 200,
  headers: Record<string, string> = {}
) => {
  await route.fulfill({ status, contentType: 'application/json', headers, body: JSON.stringify(body) });
};

test.describe('Instructor availability calendar', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(freezeDateScript, { fixedNow: '2025-05-12T12:00:00Z' });
  });

  test('persists past edits with ETag handshake', async ({ page }) => {
    let currentSchedule = structuredClone(initialSchedule);
    let currentEtag = '"v1"';
    const postedSchedules: ScheduleEntry[][] = [];
    const ifMatchHeaders: Array<string | undefined> = [];
    const baseVersions: Array<string | undefined> = [];

    await page.route('**/auth/me', (route, request) =>
      request.method() === 'GET'
        ? fulfillJson(route, {
            first_name: 'Test',
            last_name: 'Instructor',
            roles: ['instructor'],
            timezone: 'America/New_York',
          })
        : route.fallback()
    );

    await page.route('**/instructors/availability?*', (route) =>
      fulfillJson(route, buildAvailabilityRows(currentSchedule))
    );

    await page.route('**/instructors/availability/week/booked-slots?*', (route, request) =>
      request.method() === 'GET' ? fulfillJson(route, { booked_slots: bookedSlots }) : route.fallback()
    );

    await page.route('**/instructors/availability/week?*', async (route, request) => {
      if (request.method() === 'GET') {
        await fulfillJson(route, currentSchedule, 200, { ETag: currentEtag });
        return;
      }
      if (request.method() === 'POST') {
        const payload = (await request.postDataJSON()) as {
          schedule?: ScheduleEntry[];
          override?: boolean;
          base_version?: string | null;
        };
        const schedulePayload = payload?.schedule ?? [];
        const ifMatchValue = await request.headerValue('if-match');
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
            week_start: '2025-05-05',
            week_end: '2025-05-11',
            windows_created: schedulePayload.length,
            windows_updated: 0,
            windows_deleted: 0,
            version: currentEtag,
          },
          200,
          { ETag: currentEtag }
        );
        return;
      }
      await route.fallback();
    });

    await page.goto('/instructor/availability');
    await expect(page.getByText('Set Availability')).toBeVisible();

    const addPastSlotStart = page.locator('[role="gridcell"][aria-label="Monday 13:00"]');
    const addPastSlotEnd = page.locator('[role="gridcell"][aria-label="Monday 13:30"]');
    await addPastSlotStart.click();
    await addPastSlotEnd.click();
    await expect(addPastSlotEnd).toHaveAttribute('aria-pressed', 'true');

    const addFutureSlotStart = page.locator('[role="gridcell"][aria-label="Thursday 15:00"]');
    const addFutureSlotEnd = page.locator('[role="gridcell"][aria-label="Thursday 15:30"]');
    await addFutureSlotStart.click();
    await addFutureSlotEnd.click();
    await expect(addFutureSlotEnd).toHaveAttribute('aria-pressed', 'true');

    await expect(page.getByText('Unsaved changes')).toBeVisible();

    await page.getByRole('button', { name: 'Save Week' }).click();
    await expect(page.getByText('Unsaved changes')).toBeHidden();

    expect(ifMatchHeaders).toEqual(['"v1"']);
    expect(baseVersions).toEqual(['"v1"']);

    const scheduleEntries = postedSchedules.at(-1);
    expect(scheduleEntries).toBeDefined();
    if (!scheduleEntries) {
      throw new Error('Missing posted schedule payload');
    }
    expect(scheduleEntries).toEqual(
      expect.arrayContaining([
        { date: '2025-05-05', start_time: '13:00:00', end_time: '14:00:00' },
        { date: '2025-05-08', start_time: '15:00:00', end_time: '16:00:00' },
      ])
    );
  });

  test('conflict modal supports refresh and overwrite flows', async ({ page }) => {
    let currentSchedule = structuredClone(initialSchedule);
    let currentEtag = '"v1"';
    let conflictCounter = 0;
    const postedSchedules: ScheduleEntry[][] = [];
    const ifMatchHeaders: Array<string | undefined> = [];
    const baseVersions: Array<string | undefined> = [];

    await page.route('**/auth/me', (route, request) =>
      request.method() === 'GET'
        ? fulfillJson(route, {
            first_name: 'Test',
            last_name: 'Instructor',
            roles: ['instructor'],
            timezone: 'America/New_York',
          })
        : route.fallback()
    );

    await page.route('**/instructors/availability?*', (route) =>
      fulfillJson(route, buildAvailabilityRows(currentSchedule))
    );

    await page.route('**/instructors/availability/week/booked-slots?*', (route, request) =>
      request.method() === 'GET' ? fulfillJson(route, { booked_slots: bookedSlots }) : route.fallback()
    );

    await page.route('**/instructors/availability/week?*', async (route, request) => {
      if (request.method() === 'GET') {
        await fulfillJson(route, currentSchedule, 200, { ETag: currentEtag });
        return;
      }
      if (request.method() === 'POST') {
        const payload = (await request.postDataJSON()) as {
          schedule?: ScheduleEntry[];
          override?: boolean;
          base_version?: string | null;
        };
        const ifMatchValue = await request.headerValue('if-match');
        ifMatchHeaders.push(ifMatchValue ?? undefined);
        baseVersions.push(payload.base_version ?? undefined);
        const schedulePayload = payload?.schedule ?? [];
        if (!payload.override) {
          conflictCounter += 1;
          const conflictVersion = conflictCounter === 1 ? '"v2"' : '"v3"';
          currentEtag = conflictVersion;
          await fulfillJson(route, { error: 'version_conflict', current_version: conflictVersion }, 409, {
            ETag: conflictVersion,
          });
          return;
        }
        expect(ifMatchValue).toBeUndefined();
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
            week_start: '2025-05-05',
            week_end: '2025-05-11',
            windows_created: schedulePayload.length,
            windows_updated: 0,
            windows_deleted: 0,
            version: currentEtag,
          },
          200,
          { ETag: currentEtag }
        );
        return;
      }
      await route.fallback();
    });

    await page.goto('/instructor/availability');
    await expect(page.getByText('Set Availability')).toBeVisible();

    const targetCell = page.locator('[role="gridcell"][aria-label="Monday 13:00"]');
    const targetCellPair = page.locator('[role="gridcell"][aria-label="Monday 13:30"]');
    await targetCell.click();
    await targetCellPair.click();
    await expect(targetCellPair).toHaveAttribute('aria-pressed', 'true');

    await page.getByRole('button', { name: 'Save Week' }).click();

    const conflictModal = page.getByRole('dialog');
    await expect(conflictModal).toBeVisible();
    await expect(page.getByText('Latest version: "v2"')).toBeVisible();

    await page.getByRole('button', { name: 'Refresh' }).click();
    await expect(conflictModal).toBeHidden();
    await expect(targetCellPair).toHaveAttribute('aria-pressed', 'false');

    await targetCell.click();
    await targetCellPair.click();
    await expect(targetCellPair).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'Save Week' }).click();

    const conflictModalSecond = page.getByRole('dialog');
    await expect(conflictModalSecond).toBeVisible();
    await expect(page.getByText('Latest version: "v3"')).toBeVisible();

    await page.getByRole('button', { name: 'Overwrite' }).click();
    await expect(conflictModalSecond).toBeHidden();
    await expect(page.getByText('Unsaved changes')).toBeHidden();

    expect(conflictCounter).toBe(2);
    expect(ifMatchHeaders).toEqual(['"v1"', '"v2"', undefined]);
    expect(baseVersions).toEqual(['"v1"', '"v2"', '"v2"']);
    const finalSchedule = postedSchedules.at(-1);
    expect(finalSchedule).toBeDefined();
    if (!finalSchedule) {
      throw new Error('Missing final posted schedule payload');
    }
    expect(finalSchedule).toEqual(
      expect.arrayContaining([
        { date: '2025-05-05', start_time: '13:00:00', end_time: '14:00:00' },
      ])
    );
  });

  test('mobile layout renders day chips', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });

    await page.route('**/auth/me', (route, request) =>
      request.method() === 'GET'
        ? fulfillJson(route, {
            first_name: 'Test',
            last_name: 'Instructor',
            roles: ['instructor'],
            timezone: 'America/New_York',
          })
        : route.fallback()
    );

    await page.route('**/instructors/availability?*', (route) =>
      fulfillJson(route, buildAvailabilityRows(initialSchedule))
    );

    await page.route('**/instructors/availability/week?*', (route, request) =>
      request.method() === 'GET'
        ? fulfillJson(route, initialSchedule, 200, { ETag: '"v1"' })
        : route.fallback()
    );

    await page.route('**/instructors/availability/week/booked-slots?*', (route, request) =>
      request.method() === 'GET' ? fulfillJson(route, { booked_slots: [] }) : route.fallback()
    );

    await page.goto('/instructor/availability');

    const chipList = page.locator('button', { hasText: 'Mon' });
    await expect(chipList.first()).toBeVisible();
    await expect(page.locator('[role="gridcell"][aria-label="Monday 08:00"]')).toBeVisible();
  });
});
