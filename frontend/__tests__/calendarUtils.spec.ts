import { buildDaySegments, normalizeSchedule } from '@/lib/calendar/normalize';
import { fromWindows, newEmptyBits, toWindows, toggle, idx } from '@/lib/calendar/bitset';
import type { WeekSchedule } from '@/types/availability';
import type { DayBits } from '@/lib/calendar/bitset';

describe('calendar normalization', () => {
  it('splits overnight intervals across days', () => {
    const schedule: WeekSchedule = {
      '2024-03-09': [{ start_time: '23:30:00', end_time: '01:00:00' }],
    };

    const normalized = normalizeSchedule(schedule);

    expect(normalized['2024-03-09']).toEqual([
      { start_time: '23:30:00', end_time: '24:00:00' },
    ]);
    expect(normalized['2024-03-10']).toEqual([
      { start_time: '00:00:00', end_time: '01:00:00' },
    ]);
  });

  it('preserves 24:00 midnight boundaries', () => {
    const schedule: WeekSchedule = {
      '2025-01-12': [
        { start_time: '20:00:00', end_time: '24:00:00' },
        { start_time: '08:00:00', end_time: '11:00:00' },
      ],
    };

    const normalized = normalizeSchedule(schedule);

    expect(normalized['2025-01-12']).toEqual([
      { start_time: '08:00:00', end_time: '11:00:00' },
      { start_time: '20:00:00', end_time: '24:00:00' },
    ]);
  });

  it('suppresses contained sub-intervals and merges adjacency', () => {
    const schedule: WeekSchedule = {
      '2025-05-05': [
        { start_time: '09:00:00', end_time: '12:00:00' },
        { start_time: '09:30:00', end_time: '10:30:00' },
        { start_time: '12:00:00', end_time: '13:00:00' },
      ],
    };

    const normalized = normalizeSchedule(schedule);

    expect(normalized['2025-05-05']).toEqual([
      { start_time: '09:00:00', end_time: '13:00:00' },
    ]);
  });

  it('honors DST spring forward gaps in durations', () => {
    const segments = buildDaySegments('2024-03-10', [
      { start_time: '01:30:00', end_time: '03:30:00' },
    ]);

    expect(segments).toHaveLength(1);
    expect(segments[0]?.durationMinutes).toBe(60);
  });

  it('honors DST fall back double hour in durations', () => {
    const segments = buildDaySegments('2024-11-03', [
      { start_time: '01:30:00', end_time: '03:30:00' },
    ]);

    expect(segments).toHaveLength(1);
    expect(segments[0]?.durationMinutes).toBe(180);
  });

  it('merges back-to-back intervals without introducing horizontal gaps', () => {
    const schedule: WeekSchedule = {
      '2025-05-05': [
        { start_time: '09:00:00', end_time: '10:00:00' },
        { start_time: '10:00:00', end_time: '11:30:00' },
        { start_time: '12:00:00', end_time: '13:00:00' },
      ],
    };

    const normalized = normalizeSchedule(schedule);

    expect(normalized['2025-05-05']).toEqual([
      { start_time: '09:00:00', end_time: '11:30:00' },
      { start_time: '12:00:00', end_time: '13:00:00' },
    ]);
  });

  it('produces contiguous day segments for merged intervals', () => {
    const segments = buildDaySegments('2025-05-05', [
      { start_time: '09:00:00', end_time: '10:00:00' },
      { start_time: '10:00:00', end_time: '12:30:00' },
    ]);

    expect(segments).toHaveLength(1);
    expect(segments[0]?.startMinutes).toBe(9 * 60);
    expect(segments[0]?.endMinutes).toBe(12 * 60 + 30);
  });
});

describe('bitset helpers', () => {
  it('round-trips windows through fromWindows/toWindows', () => {
    const windows = [
      { start_time: '09:00:00', end_time: '11:00:00' },
      { start_time: '14:30:00', end_time: '15:30:00' },
    ];
    const bits = fromWindows(windows);
    expect(bits).toBeInstanceOf(Uint8Array);
    const back = toWindows(bits);
    expect(back).toEqual(windows);
  });

  it('merges adjacent toggled cells into a single window', () => {
    let bits: DayBits = newEmptyBits();
    const nineAmIndex = idx(9, 0);
    const nineThirtyIndex = idx(9, 30);
    const tenAmIndex = idx(10, 0);

    bits = toggle(bits, nineAmIndex, true);
    bits = toggle(bits, nineThirtyIndex, true);
    bits = toggle(bits, tenAmIndex, true);

    const windows = toWindows(bits);
    expect(windows).toHaveLength(1);
    expect(windows[0]).toEqual({ start_time: '09:00:00', end_time: '10:30:00' });
  });

  it('fills intermediate rows when simulating a drag from row 4 to row 10', () => {
    const startHour = 6;
    const indexForRow = (row: number) => {
      const hour = startHour + Math.floor(row / 2);
      const minute = row % 2 === 1 ? 30 : 0;
      return idx(hour, minute);
    };

    const applyRow = (bits: DayBits, row: number, value: boolean) =>
      toggle(bits, indexForRow(row), value);

    let bits: DayBits = newEmptyBits();
    const startRow = 4;
    const endRow = 10;
    bits = applyRow(bits, startRow, true);
    const step = endRow > startRow ? 1 : -1;
    for (let row = startRow + step; step > 0 ? row <= endRow : row >= endRow; row += step) {
      bits = applyRow(bits, row, true);
    }

    const windows = toWindows(bits);
    expect(windows).toEqual([{ start_time: '08:00:00', end_time: '11:30:00' }]);
  });
});
