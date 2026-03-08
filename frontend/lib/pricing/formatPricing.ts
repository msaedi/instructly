import type {
  ServiceFormatPriceIn,
  ServiceFormatPriceOut,
} from '@/src/api/generated/instructly.schemas';

/** The three lesson formats the backend accepts. */
export type ServiceFormat = 'student_location' | 'instructor_location' | 'online';

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
