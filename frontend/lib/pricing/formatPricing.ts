import type {
  ServiceFormatPriceIn,
  ServiceFormatPriceOut,
} from '@/src/api/generated/instructly.schemas';

/** The three lesson formats the backend accepts. */
export type ServiceFormat = 'student_location' | 'instructor_location' | 'online';
export type PublicAvailabilityLocationType =
  | ServiceFormat
  | 'neutral_location';

/**
 * UI state for per-format pricing.
 * Key present = format enabled; value = rate string for input control.
 * Omit key entirely to disable (do NOT set to undefined — strict TS).
 */
export type FormatPriceState = {
  student_location?: string;
  instructor_location?: string;
  online?: string;
};

export type FormatCardConfig = {
  format: ServiceFormat;
  label: string;
  description: string;
  floorModality: 'in_person' | 'online';
  placeholderRate: string;
};

export const FORMAT_CARD_CONFIGS: readonly FormatCardConfig[] = [
  {
    format: 'student_location',
    label: "At Student's Location",
    description:
      "You go to the student \u2014 anywhere within the service areas you've defined",
    floorModality: 'in_person',
    placeholderRate: '80',
  },
  {
    format: 'online',
    label: 'Online',
    description:
      'Live video lesson through the platform \u2014 no travel needed',
    floorModality: 'online',
    placeholderRate: '60',
  },
  {
    format: 'instructor_location',
    label: "At Instructor's Location",
    description:
      "Students come to you \u2014 whether that's your home, studio, or a public space you prefer",
    floorModality: 'in_person',
    placeholderRate: '80',
  },
] as const;

const ALL_FORMATS: readonly ServiceFormat[] = [
  'student_location',
  'instructor_location',
  'online',
];

/**
 * Convert UI state to API payload array.
 * Only includes enabled formats with non-empty rates.
 */
export function formatPricesToPayload(
  state: FormatPriceState,
): ServiceFormatPriceIn[] {
  const result: ServiceFormatPriceIn[] = [];
  for (const format of ALL_FORMATS) {
    const rate = state[format];
    if (rate !== undefined && rate !== '') {
      result.push({ format, hourly_rate: Number(rate) });
    }
  }
  return result;
}

/**
 * Convert API response array to UI state for pre-population.
 */
export function payloadToFormatPriceState(
  prices: ServiceFormatPriceOut[],
): FormatPriceState {
  const state: FormatPriceState = {};
  for (const { format, hourly_rate } of prices) {
    if (format === 'student_location' || format === 'instructor_location' || format === 'online') {
      state[format] = String(hourly_rate);
    }
  }
  return state;
}

/**
 * Returns true if at least one format has a non-empty rate string.
 */
export function hasAnyFormatEnabled(state: FormatPriceState): boolean {
  for (const format of ALL_FORMATS) {
    const rate = state[format];
    if (rate !== undefined && rate !== '') {
      return true;
    }
  }
  return false;
}

// ---------------------------------------------------------------------------
// Display helpers (student-facing)
// ---------------------------------------------------------------------------

const VALID_FORMATS: ReadonlySet<string> = new Set<string>([
  'student_location',
  'instructor_location',
  'online',
]);

/** Priority order for default format display when no filter active. */
export const FORMAT_DISPLAY_PRIORITY: readonly ServiceFormat[] = [
  'student_location',
  'online',
  'instructor_location',
];

/** Map format key to human-readable display label. */
export function formatLabel(format: ServiceFormat): string {
  const config = FORMAT_CARD_CONFIGS.find((c) => c.format === format);
  return config?.label ?? format;
}

/** Get the hourly rate for a specific format from an API response array. */
export function getFormatRate(
  formatPrices: ReadonlyArray<{ format: string; hourly_rate: number }>,
  format: string,
): number | null {
  const match = formatPrices.find((fp) => fp.format === format);
  return match ? match.hourly_rate : null;
}

/** Map a search location-filter value to the matching ServiceFormat keys. */
export function lessonTypeToFormats(lessonType: string): ServiceFormat[] {
  if (lessonType === 'online') return ['online'];
  if (lessonType === 'in_person') return ['student_location', 'instructor_location'];
  if (lessonType === 'travels') return ['student_location'];
  if (lessonType === 'studio') return ['instructor_location'];
  return ['student_location', 'online', 'instructor_location'];
}

/**
 * Map a search lesson-type filter to the exact location_type used by
 * the public availability API. In-person and unknown filters stay
 * conservative by using the travel path.
 */
export function lessonTypeToAvailabilityLocationType(
  lessonType?: string | null,
): PublicAvailabilityLocationType {
  if (lessonType === 'online') return 'online';
  if (lessonType === 'studio') return 'instructor_location';
  if (lessonType === 'travels') return 'student_location';
  return 'student_location';
}

type ContextualPrice = {
  rate: number;
  label: string;
  isFrom: boolean;
};

/**
 * Get display price based on search context.
 * - Filtered by lesson type → matched format rate + label
 * - No filter / "any" → min_hourly_rate + "from"
 */
export function getContextualPrice(
  formatPrices: ReadonlyArray<{ format: string; hourly_rate: number }>,
  minHourlyRate: number,
  lessonType?: string,
): ContextualPrice {
  if (lessonType && lessonType !== 'any') {
    const formats = lessonTypeToFormats(lessonType);
    const matches = formatPrices.filter((fp) =>
      formats.includes(fp.format as ServiceFormat),
    );
    if (matches.length > 0) {
      // For multi-format lesson types (in_person), pick the cheapest
      const best = matches.reduce((a, b) => a.hourly_rate <= b.hourly_rate ? a : b);
      return {
        rate: best.hourly_rate,
        label: formats.length > 1 ? 'In-person' : formatLabel(best.format as ServiceFormat),
        isFrom: false,
      };
    }
  }
  return { rate: minHourlyRate, label: 'from', isFrom: true };
}

/** Derive available ServiceFormat keys from a format_prices API array. */
export function availableFormatsFromPrices(
  formatPrices: ReadonlyArray<{ format: string; hourly_rate: number }>,
): ServiceFormat[] {
  return formatPrices
    .map((fp) => fp.format)
    .filter((f): f is ServiceFormat => VALID_FORMATS.has(f));
}

// ---------------------------------------------------------------------------
// Instructor-side helpers
// ---------------------------------------------------------------------------

/**
 * Compute initial format_prices for a newly-added service based on
 * whether the instructor has service areas / teaching locations.
 */
export function defaultFormatPrices(
  hasServiceAreas: boolean,
  hasTeachingLocations: boolean,
): FormatPriceState {
  const state: FormatPriceState = {};
  if (hasServiceAreas) {
    state.student_location = '';
  }
  if (hasTeachingLocations) {
    state.instructor_location = '';
  }
  if (!hasServiceAreas && !hasTeachingLocations) {
    state.online = '';
  }
  return state;
}
