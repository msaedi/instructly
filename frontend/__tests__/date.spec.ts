import { formatDateForAPI, toDateOnlyString } from '@/lib/availability/dateHelpers';

describe('date serialization invariants', () => {
  it('formats Date objects to YYYY-MM-DD without timezone drift', () => {
    const date = new Date(2025, 6, 15); // July 15, 2025 (month is 0-indexed)
    expect(formatDateForAPI(date)).toBe('2025-07-15');
  });

  it('accepts valid date strings and preserves them', () => {
    expect(toDateOnlyString('2025-07-15')).toBe('2025-07-15');
  });

  it('throws on strings containing time components', () => {
    expect(() => toDateOnlyString('2025-07-15T10:00:00Z')).toThrow(/YYYY-MM-DD/);
  });

  it('throws when value is neither Date nor string in dev/test', () => {
    // @ts-expect-error Intentionally passing invalid type to assert runtime safeguard
    expect(() => toDateOnlyString(12345)).toThrow('Date or YYYY-MM-DD string');
  });
});
