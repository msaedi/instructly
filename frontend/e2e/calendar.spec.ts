import { test, expect } from '@playwright/test';

test.describe('Instructor availability calendar', () => {
  const initialSchedule = {
    '2025-05-05': [
      { start_time: '08:00:00', end_time: '10:00:00' },
      { start_time: '23:30:00', end_time: '01:00:00' },
    ],
    '2025-05-06': [
      { start_time: '00:00:00', end_time: '02:00:00' },
      { start_time: '14:00:00', end_time: '18:00:00' },
    ],
  } as Record<string, Array<{ start_time: string; end_time: string }>>;

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

  type ScheduleEntry = { date: string; start_time: string; end_time: string };

  test('desktop edit + save', async ({ page }) => {
    let currentSchedule = structuredClone(initialSchedule);
    const postedSchedules: ScheduleEntry[][] = [];

    const fulfillJson = async (
      route: import('@playwright/test').Route,
      body: unknown,
      status = 200,
      headers: Record<string, string> = {}
    ) => {
      await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body), headers });
    };

    await page.route('**/auth/me', async (route, request) => {
      if (request.method() === 'GET') {
        await fulfillJson(route, {
          first_name: 'Test',
          last_name: 'Instructor',
          roles: ['instructor'],
          timezone: 'America/New_York',
        });
        return;
      }
      await route.fallback();
    });

    await page.route('**/instructors/availability/week?start_date=*', async (route, request) => {
      if (request.method() === 'GET') {
        await fulfillJson(route, currentSchedule, 200, { ETag: '"v1"' });
        return;
      }
      await route.fallback();
    });

    await page.route('**/instructors/availability/week/booked-slots?start_date=*', async (route, request) => {
      if (request.method() === 'GET') {
        await fulfillJson(route, { booked_slots: bookedSlots });
        return;
      }
      await route.fallback();
    });

    await page.route('**/instructors/availability/week', async (route, request) => {
      if (request.method() === 'POST') {
        const payload = (await request.postDataJSON()) as { schedule?: ScheduleEntry[] };
        const schedulePayload = payload?.schedule;
        if (!schedulePayload) {
          await fulfillJson(route, { ok: false }, 400);
          return;
        }
        postedSchedules.push(schedulePayload);
        const grouped: typeof currentSchedule = {};
        for (const entry of schedulePayload) {
          grouped[entry.date] = grouped[entry.date] || [];
          grouped[entry.date]!.push({ start_time: entry.start_time, end_time: entry.end_time });
        }
        currentSchedule = grouped;
        await fulfillJson(route, { ok: true }, 200, { ETag: '"v2"' });
        return;
      }
      await route.fallback();
    });

    await page.goto('/instructor/availability');

    await expect(page.getByText('Set Availability')).toBeVisible();

    const selectedCells = page.locator('[role="gridcell"][aria-pressed="true"]');
    await expect(selectedCells).toHaveCount(17);

    const overnightStart = page.locator('[role="gridcell"][aria-label="Monday 23:30"]');
    await expect(overnightStart).toHaveAttribute('aria-pressed', 'true');
    const overnightContinuation = page.locator('[role="gridcell"][aria-label="Tuesday 00:00"]');
    await expect(overnightContinuation).toHaveAttribute('aria-pressed', 'true');

    const targetCell = page.locator('[role="gridcell"][aria-label="Monday 09:30"]');
    await targetCell.click();
    await expect(targetCell).toHaveAttribute('aria-pressed', 'false');
    await expect(page.getByText('Unsaved changes')).toBeVisible();

    await page.getByRole('button', { name: 'Save Week' }).click();

    await expect(page.getByText('Unsaved changes')).toBeHidden();

    const scheduleEntries = postedSchedules.at(-1);
    if (!scheduleEntries) {
      throw new Error('Expected a schedule to be posted');
    }
    const mondayEntries = scheduleEntries.filter((entry) => entry.date === '2025-05-05');
    expect(mondayEntries).toEqual([
      { date: '2025-05-05', start_time: '08:00:00', end_time: '09:30:00' },
      { date: '2025-05-05', start_time: '23:30:00', end_time: '24:00:00' },
    ]);
  });

  test('mobile layout renders day chips', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.route('**/auth/me', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ first_name: 'Test', last_name: 'Instructor', roles: ['instructor'], timezone: 'America/New_York' }),
    }));

    await page.route('**/instructors/availability/week?start_date=*', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(initialSchedule),
    }));

    await page.route('**/instructors/availability/week/booked-slots?start_date=*', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ booked_slots: [] }),
    }));

    await page.goto('/instructor/availability');

    const chipList = page.locator('button', { hasText: 'Mon' });
    await expect(chipList.first()).toBeVisible();
    await expect(page.locator('[role="gridcell"][aria-label="Monday 08:00"]')).toBeVisible();
  });
});
