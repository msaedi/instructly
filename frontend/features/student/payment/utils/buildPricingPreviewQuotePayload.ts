import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import type { PricingPreviewQuotePayload, PricingPreviewQuotePayloadBase } from '@/lib/api/pricing';

type BookingForPayload = {
  instructorId: string;
  serviceId?: string;
  instructorServiceId?: string;
  date: Date | string;
  startTime: string;
  duration: number;
  location: string;
  metadata?: {
    serviceId?: string;
    modality?: string;
  };
};

export type PricingPreviewSelection = {
  instructorId: string;
  instructorServiceId: string;
  bookingDateLocalYYYYMMDD: string;
  startHHMM24: string;
  selectedDurationMinutes: number;
  modality: 'remote' | 'in_person' | 'student_home' | 'instructor_location' | 'neutral';
  meetingLocation: string;
  appliedCreditCents?: number;
};

const modalityToLocationType: Record<string, PricingPreviewQuotePayloadBase['location_type']> = {
  remote: 'remote',
  online: 'remote',
  virtual: 'remote',
  in_person: 'in_person',
  inperson: 'in_person',
  student_home: 'student_home',
  studenthome: 'student_home',
  instructor_location: 'instructor_location',
  instructorlocation: 'instructor_location',
  neutral: 'neutral',
};

const inferLocationType = (booking: BookingForPayload): PricingPreviewQuotePayloadBase['location_type'] => {
  const modality = (booking.metadata?.modality ?? '').toLowerCase();
  const location = booking.location.toLowerCase();

  if (modality) {
    const mapped = modalityToLocationType[modality.replace(/\s+/g, '_')];
    if (mapped) {
      return mapped;
    }
  }

  if (location.includes('online') || location.includes('remote') || location.includes('virtual')) {
    return 'remote';
  }

  return 'in_person';
};

const isSelection = (value: BookingForPayload | PricingPreviewSelection): value is PricingPreviewSelection =>
  typeof (value as PricingPreviewSelection)?.bookingDateLocalYYYYMMDD === 'string' &&
  typeof (value as PricingPreviewSelection)?.startHHMM24 === 'string';

const normalizeBookingInput = (
  input: BookingForPayload | PricingPreviewSelection,
): BookingForPayload => {
  if (!isSelection(input)) {
    return input;
  }

  const {
    instructorId,
    instructorServiceId,
    bookingDateLocalYYYYMMDD,
    startHHMM24,
    selectedDurationMinutes,
    modality,
    meetingLocation,
  } = input;

  return {
    instructorId,
    serviceId: instructorServiceId,
    instructorServiceId,
    date: bookingDateLocalYYYYMMDD,
    startTime: startHHMM24,
    duration: selectedDurationMinutes,
    location: meetingLocation,
    metadata: {
      serviceId: instructorServiceId,
      modality,
    },
  };
};

export function buildPricingPreviewQuotePayloadBase(
  bookingInput: BookingForPayload | PricingPreviewSelection,
): PricingPreviewQuotePayloadBase {
  const booking = normalizeBookingInput(bookingInput);
  const instructorServiceId =
    booking.instructorServiceId ?? booking.serviceId ?? booking.metadata?.serviceId ?? '';
  const bookingDateSource = booking.date instanceof Date ? booking.date : new Date(`${booking.date}T00:00:00`);
  const bookingDate = formatDateForAPI(bookingDateSource);
  const locationType = inferLocationType(booking);

  return {
    instructor_id: booking.instructorId,
    instructor_service_id: instructorServiceId,
    booking_date: bookingDate,
    start_time: booking.startTime,
    selected_duration: booking.duration,
    location_type: locationType,
    meeting_location: booking.location,
  };
}

export function buildPricingPreviewQuotePayload(
  bookingInput: BookingForPayload | PricingPreviewSelection,
  appliedCreditCents?: number,
): PricingPreviewQuotePayload {
  const selectionCredit = isSelection(bookingInput) ? bookingInput.appliedCreditCents : undefined;
  const creditValue = appliedCreditCents ?? selectionCredit ?? 0;

  return {
    ...buildPricingPreviewQuotePayloadBase(bookingInput),
    applied_credit_cents: Math.max(0, Math.round(creditValue)),
  };
}
