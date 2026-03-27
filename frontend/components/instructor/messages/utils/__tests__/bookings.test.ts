import {
  formatBookingInfo,
  formatDateShort,
  formatTime12h,
  getBookingStatus,
  getBookingStatusLabel,
  getBookingTimestamp,
} from '../bookings';

describe('booking format helpers', () => {
  it('returns an empty string when the date is missing', () => {
    expect(formatDateShort()).toBe('');
  });

  it('falls back to the raw date when parsing fails', () => {
    expect(formatDateShort('not-a-date')).toBe('not-a-date');
  });

  it('returns an empty string when the time is missing', () => {
    expect(formatTime12h()).toBe('');
  });

  it('falls back to the raw time when parsing fails', () => {
    expect(formatTime12h('invalid')).toBe('invalid');
  });

  it('formats valid booking details into a readable summary', () => {
    expect(
      formatBookingInfo({
        service_name: 'Piano Lesson',
        date: '2025-01-20',
        start_time: '09:00',
      })
    ).toBe('Piano Lesson on Jan 20, 9am');
  });

  it('falls back to the raw date format when both date and time stay unformatted', () => {
    expect(
      formatBookingInfo({
        service_name: 'Piano Lesson',
        date: 'not-a-date',
        start_time: 'invalid',
      })
    ).toBe('Piano Lesson - not-a-date');
  });
});

describe('getBookingTimestamp', () => {
  it('returns the parsed timestamp when the booking date and time are valid', () => {
    expect(
      getBookingTimestamp({
        date: '2025-01-20',
        start_time: '09:00',
      })
    ).toBe(Date.parse('2025-01-20T09:00'));
  });

  it('falls back to 0 by default when the booking date is invalid', () => {
    expect(
      getBookingTimestamp({
        date: 'not-a-date',
        start_time: '09:00',
      })
    ).toBe(0);
  });

  it('supports an explicit fallback value', () => {
    expect(
      getBookingTimestamp(
        {
          date: 'not-a-date',
          start_time: '09:00',
        },
        Number.POSITIVE_INFINITY
      )
    ).toBe(Number.POSITIVE_INFINITY);
  });

  it('falls back when the date and time fields are missing', () => {
    expect(getBookingTimestamp({}, Number.POSITIVE_INFINITY)).toBe(Number.POSITIVE_INFINITY);
  });
});

describe('booking status helpers', () => {
  it('prefers an explicit booking status when one is present', () => {
    expect(
      getBookingStatus(
        {
          date: '2025-01-20',
          start_time: '09:00',
          status: ' cancelled ',
        },
        Date.parse('2025-01-19T00:00:00Z')
      )
    ).toBe('CANCELLED');
  });

  it('derives a completed status when the booking time is in the past', () => {
    expect(
      getBookingStatus(
        {
          date: '2025-01-20',
          start_time: '09:00',
        },
        Date.parse('2025-01-21T00:00:00Z')
      )
    ).toBe('COMPLETED');
  });

  it('formats unknown status labels into title case words', () => {
    expect(getBookingStatusLabel('PAYMENT_PENDING')).toBe('Payment Pending');
  });
});
