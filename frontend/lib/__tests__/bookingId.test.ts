import { shortenBookingId } from '../bookingId';

describe('shortenBookingId', () => {
  it('formats a ULID as XXX-YYYY using the display slice from the design spec', () => {
    expect(shortenBookingId('01KKQKWD9V9QF0J2T0AB3124')).toBe('KWD-3124');
    expect(shortenBookingId('01JZ7AKD1234567890ABCDXYZ')).toBe('AKD-DXYZ');
  });

  it('returns the normalized value when the string is too short to shorten safely', () => {
    expect(shortenBookingId('abc123')).toBe('ABC123');
  });
});
