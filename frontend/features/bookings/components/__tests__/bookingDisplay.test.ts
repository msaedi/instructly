import {
  formatBookingCardDate,
  formatBookingTimeRange,
  getBookingStatusLabel,
} from '../bookingDisplay';

describe('bookingDisplay helpers', () => {
  it('falls back to Pending when the status is missing', () => {
    expect(getBookingStatusLabel(undefined)).toBe('Pending');
    expect(getBookingStatusLabel(null)).toBe('Pending');
  });

  it('humanizes unknown statuses', () => {
    expect(getBookingStatusLabel('WEIRD_STATUS')).toBe('Weird Status');
  });

  it('falls back to the raw booking date when parsing fails', () => {
    expect(formatBookingCardDate('not-a-date', '10:00:00')).toBe('not-a-date');
  });

  it('falls back to the raw booking times when parsing fails', () => {
    expect(formatBookingTimeRange('not-a-date', 'bad-start', 'bad-end')).toBe(
      'bad-start – bad-end'
    );
  });
});
