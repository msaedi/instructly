import { buildDaySegments, normalizeSchedule } from '@/lib/calendar/normalize';
import type { WeekSchedule } from '@/types/availability';

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
});
