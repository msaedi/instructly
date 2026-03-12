import { expandDiscreteStarts } from '../expandDiscreteStarts';

describe('expandDiscreteStarts', () => {
  it('should produce times on 15-min boundaries from aligned start', () => {
    // 10:00-11:00 with 15-min step, 30-min duration
    const result = expandDiscreteStarts('10:00:00', '11:00:00', 15, 30);
    expect(result).toEqual(['10:00am', '10:15am', '10:30am']);
  });

  it('should snap up to next 15-min boundary from 5-min offset start', () => {
    // 10:05-11:00 with 15-min step, 30-min duration
    // 10:05 snaps to 10:15, then 10:15 + 30 = 10:45 <= 11:00 ✓
    // 10:30 + 30 = 11:00 <= 11:00 ✓
    // 10:45 + 30 = 11:15 > 11:00 ✗
    const result = expandDiscreteStarts('10:05:00', '11:00:00', 15, 30);
    expect(result).toEqual(['10:15am', '10:30am']);
  });

  it('should snap up from 10-min offset', () => {
    // 10:10-11:00 with 15-min step, 30-min duration
    // 10:10 snaps to 10:15
    const result = expandDiscreteStarts('10:10:00', '11:00:00', 15, 30);
    expect(result).toEqual(['10:15am', '10:30am']);
  });

  it('should not snap when already on step boundary', () => {
    // 10:15 is already on 15-min boundary — no snap needed
    const result = expandDiscreteStarts('10:15:00', '11:00:00', 15, 30);
    expect(result).toEqual(['10:15am', '10:30am']);
  });

  it('should return empty when snapped start leaves no room', () => {
    // 10:50-11:00 with 15-min step, 30-min duration
    // 10:50 snaps to 11:00, but 11:00 + 30 > 11:00
    const result = expandDiscreteStarts('10:50:00', '11:00:00', 15, 30);
    expect(result).toEqual([]);
  });

  it('should handle PM times correctly', () => {
    // 13:05-14:00 with 15-min step, 30-min duration
    // 13:05 snaps to 13:15
    const result = expandDiscreteStarts('13:05:00', '14:00:00', 15, 30);
    expect(result).toEqual(['1:15pm', '1:30pm']);
  });
});
