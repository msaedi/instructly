import { overlapsHHMM, minutesSinceHHMM } from '../overlap';

describe('time overlap utilities', () => {
  it('converts HH:MM into minutes since midnight', () => {
    expect(minutesSinceHHMM('00:00')).toBe(0);
    expect(minutesSinceHHMM('09:30')).toBe(9 * 60 + 30);
    expect(minutesSinceHHMM('23:59')).toBe(23 * 60 + 59);
  });

  it('throws on invalid HH:MM strings', () => {
    expect(() => minutesSinceHHMM('')).toThrow();
    expect(() => minutesSinceHHMM('25:00')).toThrow();
    expect(() => minutesSinceHHMM('10:99')).toThrow();
  });

  it('detects overlapping ranges', () => {
    expect(overlapsHHMM('09:00', 60, '09:30', 30)).toBe(true);
    expect(overlapsHHMM('13:15', 45, '14:00', 30)).toBe(false);
    expect(overlapsHHMM('08:00', 30, '08:30', 60)).toBe(false);
  });

  it('treats touching boundaries as non-overlapping', () => {
    expect(overlapsHHMM('10:00', 30, '10:30', 30)).toBe(false);
    expect(overlapsHHMM('10:30', 30, '10:00', 30)).toBe(false);
  });

  it('handles AM/PM conversions by using 24h inputs', () => {
    expect(overlapsHHMM('14:00', 60, '15:00', 30)).toBe(false);
    expect(overlapsHHMM('14:00', 90, '15:15', 45)).toBe(true);
  });
});
