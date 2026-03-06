import { at } from '@/lib/ts/safe';
import {
  computeBasePriceCents,
  computePriceFloorCents,
  type NormalizedModality,
  type PriceFloorConfig,
} from '@/lib/pricing/priceFloors';

export type ParsedDisplayedTime =
  | {
      ok: true;
      normalizedTimeHHMM: string;
      hour: number;
      minute: number;
    }
  | {
      ok: false;
      kind: 'format';
      selectedTime: string;
    }
  | {
      ok: false;
      kind: 'values';
      selectedTime: string;
      hourStr: string;
      minuteStr: string;
    };

export const reconcileTimeSelection = ({
  selectedTime,
  timeSlots,
  preferredTime,
}: {
  selectedTime: string | null;
  timeSlots: string[];
  preferredTime: string | null;
}): string | null => {
  if (timeSlots.length === 0) {
    return null;
  }

  if (selectedTime && timeSlots.includes(selectedTime)) {
    return selectedTime;
  }

  if (preferredTime && timeSlots.includes(preferredTime)) {
    return preferredTime;
  }

  return timeSlots[0] ?? null;
};

export const formatAvailabilityDateLabel = (isoDate: string): string => {
  if (!isoDate) {
    return '';
  }

  const parsed = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return isoDate;
  }
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric' }).format(parsed);
};

export const parseDisplayedTime = (selectedTime: string): ParsedDisplayedTime => {
  const timeWithoutAmPm = selectedTime.replace(/[ap]m/gi, '').trim();
  const timeParts = timeWithoutAmPm.split(':');
  const hourStr = at(timeParts, 0);
  const minuteStr = at(timeParts, 1);

  if (!hourStr || !minuteStr) {
    return {
      ok: false,
      kind: 'format',
      selectedTime,
    };
  }

  if (timeParts.length !== 2) {
    return {
      ok: false,
      kind: 'format',
      selectedTime,
    };
  }

  let hour = Number.parseInt(hourStr, 10);
  const minute = Number.parseInt(minuteStr, 10);

  if (!Number.isFinite(hour) || !Number.isFinite(minute)) {
    return {
      ok: false,
      kind: 'values',
      hourStr,
      minuteStr,
      selectedTime,
    };
  }

  const isAM = selectedTime.toLowerCase().includes('am');
  const isPM = selectedTime.toLowerCase().includes('pm');

  if (isPM && hour !== 12) hour += 12;
  if (isAM && hour === 12) hour = 0;

  return {
    ok: true,
    normalizedTimeHHMM: `${hour.toString().padStart(2, '0')}:${minute
      .toString()
      .padStart(2, '0')}`,
    hour,
    minute,
  };
};

export const buildBookingDateTime = (selectedDate: string, startTime: string): Date | null => {
  const bookingDateTime = new Date(`${selectedDate}T${startTime}`);
  return Number.isNaN(bookingDateTime.getTime()) ? null : bookingDateTime;
};

export const parseDisplayTimeToMinutes = (display: string): number => {
  const lower = display.toLowerCase();
  const isPM = lower.includes('pm');
  const isAM = lower.includes('am');
  const core = lower.replace(/am|pm/g, '').trim();
  const [hh, mm] = core.split(':');
  if (!hh || !mm) return 0;
  let hour = parseInt(hh, 10);
  const minute = parseInt(mm || '0', 10);
  if (isPM && hour !== 12) hour += 12;
  if (!isPM && isAM && hour === 12) hour = 0;
  return hour * 60 + minute;
};

export const areNumberSetsEqual = (a: number[], b: number[]): boolean => {
  if (a.length !== b.length) return false;
  const setA = new Set(a);
  for (const value of b) {
    if (!setA.has(value)) return false;
  }
  return true;
};

export const getPriceFloorViolation = ({
  pricingFloors,
  hasSelectedService,
  selectedHourlyRate,
  selectedDuration,
  selectedModality,
}: {
  pricingFloors: PriceFloorConfig | null | undefined;
  hasSelectedService: boolean;
  selectedHourlyRate: number;
  selectedDuration: number;
  selectedModality: NormalizedModality;
}): { floorCents: number; baseCents: number } | null => {
  if (!pricingFloors) return null;
  if (!hasSelectedService) return null;
  if (!Number.isFinite(selectedHourlyRate) || selectedHourlyRate <= 0) return null;
  if (!Number.isFinite(selectedDuration) || selectedDuration <= 0) return null;

  const floorCents = computePriceFloorCents(pricingFloors, selectedModality, selectedDuration);
  const baseCents = computeBasePriceCents(selectedHourlyRate, selectedDuration);
  if (baseCents < floorCents) {
    return { floorCents, baseCents };
  }
  return null;
};

export type PreparedBookingTiming =
  | {
      ok: true;
      parsedTime: Extract<ParsedDisplayedTime, { ok: true }>;
      startTime: string;
      endTime: string;
      bookingDateTime: Date;
    }
  | {
      ok: false;
      logMessage: 'Invalid time format' | 'Invalid time values' | 'Invalid booking date/time';
      logContext: Record<string, string>;
    };

export const consumePreparedBookingTiming = (
  preparedTiming: PreparedBookingTiming,
  logError: (message: string, context: Record<string, string>) => void,
): Extract<PreparedBookingTiming, { ok: true }> | null => {
  if (!preparedTiming.ok) {
    logError(preparedTiming.logMessage, preparedTiming.logContext);
    return null;
  }

  return preparedTiming;
};

export const prepareBookingTiming = ({
  selectedDate,
  selectedTime,
  selectedDuration,
}: {
  selectedDate: string;
  selectedTime: string;
  selectedDuration: number;
}): PreparedBookingTiming => {
  const parsedTime = parseDisplayedTime(selectedTime);
  if (!parsedTime.ok) {
    if (parsedTime.kind === 'values') {
      return {
        ok: false,
        logMessage: 'Invalid time values',
        logContext: {
          hourStr: parsedTime.hourStr,
          minuteStr: parsedTime.minuteStr,
          selectedTime,
        },
      };
    }

    return {
      ok: false,
      logMessage: 'Invalid time format',
      logContext: { selectedTime },
    };
  }

  const { hour, minute, normalizedTimeHHMM } = parsedTime;
  let endHour = hour + Math.floor(selectedDuration / 60);
  let endMinute = minute + (selectedDuration % 60);

  if (endMinute >= 60) {
    endHour += Math.floor(endMinute / 60);
    endMinute %= 60;
  }

  const startTime = `${normalizedTimeHHMM}:00`;
  const endTime = `${endHour.toString().padStart(2, '0')}:${endMinute
    .toString()
    .padStart(2, '0')}:00`;
  const bookingDateTime = buildBookingDateTime(selectedDate, startTime);

  if (!bookingDateTime) {
    return {
      ok: false,
      logMessage: 'Invalid booking date/time',
      logContext: {
        dateTimeString: `${selectedDate}T${startTime}`,
        selectedDate,
        startTime,
      },
    };
  }

  return {
    ok: true,
    parsedTime,
    startTime,
    endTime,
    bookingDateTime,
  };
};
