export const buildDisplayDate = (value: string | Date | null | undefined): Date | null => {
  if (!value) {
    return null;
  }
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const isoCandidate = typeof value === 'string' ? value.trim() : String(value);
  if (!isoCandidate) {
    return null;
  }
  const parsed = new Date(`${isoCandidate}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
};

export const shouldIgnoreAddressSuggestionSelection = (
  suggestion: unknown,
  isTravelLocation: boolean,
): boolean => !suggestion || !isTravelLocation;

export const getLocationTypeForManualChange = (
  isTravelLocation: boolean,
): 'student_location' | null => (isTravelLocation ? null : 'student_location');

export const applyManualLocationChange = ({
  isTravelLocation,
  setLocationType,
  setSelectedPublicSpace,
  setIsEditingLocation,
  setAddressDetailsError,
  onClearFloorViolation,
}: {
  isTravelLocation: boolean;
  setLocationType: (value: 'student_location') => void;
  setSelectedPublicSpace: (value: null) => void;
  setIsEditingLocation: (value: boolean) => void;
  setAddressDetailsError: (value: string | null) => void;
  onClearFloorViolation?: (() => void) | null | undefined;
}): void => {
  const nextLocationType = getLocationTypeForManualChange(isTravelLocation);
  if (nextLocationType) {
    setLocationType(nextLocationType);
  }
  setSelectedPublicSpace(null);
  setIsEditingLocation(true);
  setAddressDetailsError(null);
  onClearFloorViolation?.();
};

export type PromoActionResolution =
  | {
      kind: 'error';
      message: string;
    }
  | {
      kind: 'remove';
    }
  | {
      kind: 'apply';
    };

export const resolvePromoAction = ({
  referralActive,
  promoActive,
  promoCode,
}: {
  referralActive: boolean;
  promoActive: boolean;
  promoCode: string;
}): PromoActionResolution => {
  if (referralActive) {
    return {
      kind: 'error',
      message: 'Referral credit can’t be combined with a promo code.',
    };
  }
  if (promoActive) {
    return { kind: 'remove' };
  }
  if (!promoCode.trim()) {
    return {
      kind: 'error',
      message: 'Enter a promo code to apply.',
    };
  }
  return { kind: 'apply' };
};

type ConflictKey = {
  bookingDate: string;
  startHHMM24: string;
  durationMinutes: number;
};

type ConflictListItem = {
  booking_date?: string;
  start_time?: string;
  end_time?: string | null;
  duration_minutes?: number | null;
  status?: string;
};

export const hasRelevantConflict = (
  existing: ConflictListItem | null | undefined,
  key: ConflictKey,
  relevantStatuses: Set<string>,
  to24HourTime: (value: string) => string,
  minutesSinceHHMM: (value: string) => number,
  overlapsHHMM: (
    startA: string,
    durationA: number,
    startB: string,
    durationB: number,
  ) => boolean,
): boolean => {
  if (!existing) {
    return false;
  }
  if (existing.booking_date && existing.booking_date !== key.bookingDate) {
    return false;
  }
  if (existing.status && !relevantStatuses.has(existing.status.toLowerCase())) {
    return false;
  }
  if (!existing.start_time) {
    return false;
  }

  let existingStart: string;
  try {
    existingStart = to24HourTime(String(existing.start_time));
  } catch {
    return false;
  }

  let existingDuration = Number.isFinite(existing.duration_minutes)
    ? Math.round(Number(existing.duration_minutes))
    : null;

  if (!existingDuration || existingDuration <= 0) {
    if (existing.end_time) {
      try {
        const startMinutes = minutesSinceHHMM(existingStart);
        const endMinutes = minutesSinceHHMM(to24HourTime(String(existing.end_time)));
        const diff = endMinutes - startMinutes;
        existingDuration = diff > 0 ? diff : null;
      } catch {
        existingDuration = null;
      }
    }
  }

  if (!existingDuration || existingDuration <= 0) {
    return false;
  }

  return overlapsHHMM(key.startHHMM24, key.durationMinutes, existingStart, existingDuration);
};

export const getClientFloorViolation = <TPricingFloors, TModality extends string>(
  pricingFloors: TPricingFloors | null,
  hourlyRate: number,
  durationMinutes: number,
  selectedModality: TModality,
  computePriceFloorCents: (
    pricingFloors: TPricingFloors,
    selectedModality: TModality,
    durationMinutes: number,
  ) => number,
  computeBasePriceCents: (hourlyRate: number, durationMinutes: number) => number,
): { floorCents: number; baseCents: number } | null => {
  if (!pricingFloors) {
    return null;
  }
  if (!Number.isFinite(hourlyRate) || hourlyRate <= 0) {
    return null;
  }
  if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
    return null;
  }
  const floorCents = computePriceFloorCents(pricingFloors, selectedModality, durationMinutes);
  const baseCents = computeBasePriceCents(hourlyRate, durationMinutes);
  if (baseCents < floorCents) {
    return { floorCents, baseCents };
  }
  return null;
};
