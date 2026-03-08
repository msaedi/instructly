import type { ServiceFormatPriceOut } from '@/src/api/generated/instructly.schemas';
import {
  formatLabel,
  getFormatRate,
  lessonTypeToFormats,
  getContextualPrice,
  availableFormatsFromPrices,
  FORMAT_DISPLAY_PRIORITY,
} from '../formatPricing';

const samplePrices: ServiceFormatPriceOut[] = [
  { format: 'student_location', hourly_rate: 120 },
  { format: 'online', hourly_rate: 90 },
  { format: 'instructor_location', hourly_rate: 100 },
];

describe('formatLabel', () => {
  it('returns "Online" for online format', () => {
    expect(formatLabel('online')).toBe('Online');
  });

  it("returns \"At Student's Location\" for student_location", () => {
    expect(formatLabel('student_location')).toBe("At Student's Location");
  });

  it("returns \"At Instructor's Location\" for instructor_location", () => {
    expect(formatLabel('instructor_location')).toBe("At Instructor's Location");
  });
});

describe('getFormatRate', () => {
  it('returns the hourly rate for a matching format', () => {
    expect(getFormatRate(samplePrices, 'online')).toBe(90);
  });

  it('returns null when format is not in the array', () => {
    expect(getFormatRate([], 'online')).toBeNull();
  });

  it('returns null for an unknown format string', () => {
    expect(getFormatRate(samplePrices, 'unknown')).toBeNull();
  });
});

describe('lessonTypeToFormats', () => {
  it('maps "online" to online format', () => {
    expect(lessonTypeToFormats('online')).toEqual(['online']);
  });

  it('maps "travels" to student_location format', () => {
    expect(lessonTypeToFormats('travels')).toEqual(['student_location']);
  });

  it('maps "studio" to instructor_location format', () => {
    expect(lessonTypeToFormats('studio')).toEqual(['instructor_location']);
  });

  it('maps "in_person" to student_location and instructor_location', () => {
    expect(lessonTypeToFormats('in_person')).toEqual([
      'student_location',
      'instructor_location',
    ]);
  });

  it('maps "any" to all formats', () => {
    expect(lessonTypeToFormats('any')).toEqual([
      'student_location',
      'online',
      'instructor_location',
    ]);
  });

  it('maps unknown value to all formats', () => {
    expect(lessonTypeToFormats('something_else')).toEqual([
      'student_location',
      'online',
      'instructor_location',
    ]);
  });
});

describe('getContextualPrice', () => {
  it('returns matched format rate when lesson type filter is active', () => {
    const result = getContextualPrice(samplePrices, 90, 'online');
    expect(result).toEqual({ rate: 90, label: 'Online', isFrom: false });
  });

  it('returns student_location rate when filtered by "travels"', () => {
    const result = getContextualPrice(samplePrices, 90, 'travels');
    expect(result).toEqual({ rate: 120, label: "At Student's Location", isFrom: false });
  });

  it('returns cheapest in-person rate with "In-person" label when filtered by "in_person"', () => {
    const result = getContextualPrice(samplePrices, 90, 'in_person');
    // instructor_location=100 is cheaper than student_location=120
    expect(result).toEqual({ rate: 100, label: 'In-person', isFrom: false });
  });

  it('returns the only in-person rate when only one in-person format exists', () => {
    const prices: ServiceFormatPriceOut[] = [
      { format: 'student_location', hourly_rate: 110 },
      { format: 'online', hourly_rate: 80 },
    ];
    const result = getContextualPrice(prices, 80, 'in_person');
    expect(result).toEqual({ rate: 110, label: 'In-person', isFrom: false });
  });

  it('returns min_hourly_rate with "from" when no filter', () => {
    const result = getContextualPrice(samplePrices, 90);
    expect(result).toEqual({ rate: 90, label: 'from', isFrom: true });
  });

  it('returns min_hourly_rate with "from" when filter is "any"', () => {
    const result = getContextualPrice(samplePrices, 90, 'any');
    expect(result).toEqual({ rate: 90, label: 'from', isFrom: true });
  });

  it('returns min_hourly_rate when filter matches no format', () => {
    const prices: ServiceFormatPriceOut[] = [{ format: 'online', hourly_rate: 80 }];
    const result = getContextualPrice(prices, 80, 'studio');
    expect(result).toEqual({ rate: 80, label: 'from', isFrom: true });
  });

  it('returns 0 with "from" when format_prices is empty', () => {
    const result = getContextualPrice([], 0);
    expect(result).toEqual({ rate: 0, label: 'from', isFrom: true });
  });
});

describe('availableFormatsFromPrices', () => {
  it('extracts all format keys from format_prices', () => {
    expect(availableFormatsFromPrices(samplePrices)).toEqual([
      'student_location',
      'online',
      'instructor_location',
    ]);
  });

  it('returns empty array for empty format_prices', () => {
    expect(availableFormatsFromPrices([])).toEqual([]);
  });

  it('only includes valid ServiceFormat keys', () => {
    const prices = [
      { format: 'online', hourly_rate: 80 },
      { format: 'unknown_format', hourly_rate: 50 },
    ] as ServiceFormatPriceOut[];
    expect(availableFormatsFromPrices(prices)).toEqual(['online']);
  });
});

describe('FORMAT_DISPLAY_PRIORITY', () => {
  it('has student_location first, online second, instructor_location third', () => {
    expect(FORMAT_DISPLAY_PRIORITY).toEqual([
      'student_location',
      'online',
      'instructor_location',
    ]);
  });
});
