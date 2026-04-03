import {
  formatBookingDate,
  formatBookingDateTime,
  formatBookingTime,
  resolveBookingDateTimes,
} from '@/lib/timezone/formatBookingTime';

describe('formatBookingTime', () => {
  it('formats UTC time to viewer timezone', () => {
    const booking = {
      booking_start_utc: '2025-12-25T19:00:00Z',
    };

    const result = formatBookingTime(booking, 'America/New_York');
    expect(result).toContain('2:00');
    expect(result).toContain('PM');
  });

  it('handles PST timezone', () => {
    const booking = {
      booking_start_utc: '2025-12-25T19:00:00Z',
    };

    const result = formatBookingTime(booking, 'America/Los_Angeles');
    expect(result).toContain('11:00');
    expect(result).toContain('AM');
  });

  it('falls back to legacy fields when UTC is not available', () => {
    const booking = {
      booking_date: '2025-12-25',
      start_time: '14:00',
    };

    const result = formatBookingTime(booking);
    expect(result).toContain('2:00');
  });
});

describe('formatBookingDate', () => {
  it('formats UTC date in viewer timezone', () => {
    const booking = {
      booking_start_utc: '2025-12-25T19:00:00Z',
    };

    const result = formatBookingDate(booking, 'America/New_York');
    expect(result).toContain('Dec');
    expect(result).toContain('25');
  });
});

describe('formatBookingDateTime', () => {
  it('formats full datetime with timezone name', () => {
    const booking = {
      booking_start_utc: '2025-12-25T19:00:00Z',
    };

    const result = formatBookingDateTime(booking, 'America/New_York');
    expect(result).toContain('Dec');
    expect(result).toContain('2:00');
    expect(result).toMatch(/E[SD]T/);
  });
});

describe('resolveBookingDateTimes', () => {
  it('honors lesson_timezone when UTC fields are missing', () => {
    const result = resolveBookingDateTimes({
      booking_date: '2026-04-02',
      start_time: '18:15:00',
      end_time: '19:15:00',
      lesson_timezone: 'America/New_York',
    });

    expect(result.start?.toISOString()).toBe('2026-04-02T22:15:00.000Z');
    expect(result.end?.toISOString()).toBe('2026-04-02T23:15:00.000Z');
  });

  it('derives the end time from duration_minutes in lesson_timezone when end_time is missing', () => {
    const result = resolveBookingDateTimes({
      booking_date: '2026-01-10',
      start_time: '09:00:00',
      duration_minutes: 45,
      lesson_timezone: 'America/Los_Angeles',
    });

    expect(result.start?.toISOString()).toBe('2026-01-10T17:00:00.000Z');
    expect(result.end?.toISOString()).toBe('2026-01-10T17:45:00.000Z');
  });
});
