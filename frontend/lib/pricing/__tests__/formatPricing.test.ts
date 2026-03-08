import {
  FORMAT_CARD_CONFIGS,
  formatPricesToPayload,
  payloadToFormatPriceState,
  hasAnyFormatEnabled,
  defaultFormatPrices,
  type FormatPriceState,
} from '../formatPricing';

describe('FORMAT_CARD_CONFIGS', () => {
  it('defines exactly three formats in order: student_location, online, instructor_location', () => {
    expect(FORMAT_CARD_CONFIGS.map((c) => c.format)).toEqual([
      'student_location',
      'online',
      'instructor_location',
    ]);
  });

  it('maps student_location and instructor_location to in_person floor, online to online floor', () => {
    const studentLoc = FORMAT_CARD_CONFIGS.find((c) => c.format === 'student_location');
    const instructorLoc = FORMAT_CARD_CONFIGS.find((c) => c.format === 'instructor_location');
    const online = FORMAT_CARD_CONFIGS.find((c) => c.format === 'online');

    expect(studentLoc?.floorModality).toBe('in_person');
    expect(instructorLoc?.floorModality).toBe('in_person');
    expect(online?.floorModality).toBe('online');
  });
});

describe('formatPricesToPayload', () => {
  it('converts enabled formats with non-empty rates to payload array', () => {
    const state: FormatPriceState = {
      student_location: '120',
      online: '80',
    };
    const result = formatPricesToPayload(state);
    expect(result).toEqual([
      { format: 'student_location', hourly_rate: 120 },
      { format: 'online', hourly_rate: 80 },
    ]);
  });

  it('skips formats with empty string rates', () => {
    const state: FormatPriceState = {
      student_location: '',
      online: '60',
    };
    const result = formatPricesToPayload(state);
    expect(result).toEqual([{ format: 'online', hourly_rate: 60 }]);
  });

  it('returns empty array when no formats are enabled', () => {
    const state: FormatPriceState = {};
    expect(formatPricesToPayload(state)).toEqual([]);
  });

  it('handles all three formats enabled', () => {
    const state: FormatPriceState = {
      student_location: '100',
      instructor_location: '90',
      online: '70',
    };
    const result = formatPricesToPayload(state);
    expect(result).toHaveLength(3);
    expect(result.map((r) => r.format).sort()).toEqual([
      'instructor_location',
      'online',
      'student_location',
    ]);
  });

  it('converts string rates to numbers', () => {
    const state: FormatPriceState = { online: '99.50' };
    const result = formatPricesToPayload(state);
    expect(result[0]?.hourly_rate).toBe(99.5);
    expect(typeof result[0]?.hourly_rate).toBe('number');
  });
});

describe('payloadToFormatPriceState', () => {
  it('converts API response array to FormatPriceState', () => {
    const prices = [
      { format: 'student_location' as const, hourly_rate: 120 },
      { format: 'online' as const, hourly_rate: 80 },
    ];
    const result = payloadToFormatPriceState(prices);
    expect(result).toEqual({
      student_location: '120',
      online: '80',
    });
  });

  it('returns empty object for empty array', () => {
    expect(payloadToFormatPriceState([])).toEqual({});
  });

  it('handles all three formats', () => {
    const prices = [
      { format: 'student_location' as const, hourly_rate: 100 },
      { format: 'instructor_location' as const, hourly_rate: 90 },
      { format: 'online' as const, hourly_rate: 70 },
    ];
    const result = payloadToFormatPriceState(prices);
    expect(result).toEqual({
      student_location: '100',
      instructor_location: '90',
      online: '70',
    });
  });
});

describe('hasAnyFormatEnabled', () => {
  it('returns false for empty state', () => {
    expect(hasAnyFormatEnabled({})).toBe(false);
  });

  it('returns false when all present formats have empty rates', () => {
    const state: FormatPriceState = { student_location: '', online: '' };
    expect(hasAnyFormatEnabled(state)).toBe(false);
  });

  it('returns true when at least one format has a non-empty rate', () => {
    const state: FormatPriceState = { student_location: '', online: '60' };
    expect(hasAnyFormatEnabled(state)).toBe(true);
  });

  it('returns true when format has rate "0"', () => {
    const state: FormatPriceState = { online: '0' };
    expect(hasAnyFormatEnabled(state)).toBe(true);
  });
});

describe('defaultFormatPrices', () => {
  it('enables student_location when hasServiceAreas is true', () => {
    const result = defaultFormatPrices(true, false);
    expect('student_location' in result).toBe(true);
    expect(result.student_location).toBe('');
  });

  it('enables instructor_location when hasTeachingLocations is true', () => {
    const result = defaultFormatPrices(false, true);
    expect('instructor_location' in result).toBe(true);
    expect(result.instructor_location).toBe('');
  });

  it('enables online only when neither service areas nor teaching locations exist', () => {
    const result = defaultFormatPrices(false, false);
    expect('online' in result).toBe(true);
    expect('student_location' in result).toBe(false);
    expect('instructor_location' in result).toBe(false);
  });

  it('enables both in-person formats when both areas exist', () => {
    const result = defaultFormatPrices(true, true);
    expect('student_location' in result).toBe(true);
    expect('instructor_location' in result).toBe(true);
    expect('online' in result).toBe(false);
  });
});
