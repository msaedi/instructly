import {
  formatBookingDate,
  formatBookingDateTime,
  formatBookingTime,
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
    expect(result).toContain('EST');
  });
});
