import { formatDateForAPI } from '@/lib/availability/dateHelpers';
import type { PricingPreviewQuotePayload, PricingPreviewQuotePayloadBase } from '@/lib/api/pricing';
import {
  getGenericMeetingLocationLabel,
  resolveLocationType,
  sanitizeMeetingLocation,
} from './locationUtils';

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
    location_type?: string;
  };
};

export type PricingPreviewSelection = {
  instructorId: string;
  instructorServiceId: string;
  bookingDateLocalYYYYMMDD: string;
  startHHMM24: string;
  selectedDurationMinutes: number;
  modality:
    | 'remote'
    | 'in_person'
    | 'student_location'
    | 'instructor_location'
    | 'neutral_location';
  meetingLocation: string;
  appliedCreditCents?: number;
};

const inferLocationType = (booking: BookingForPayload): PricingPreviewQuotePayloadBase['location_type'] => {
  const metadata = booking.metadata ?? {};
  return resolveLocationType({
    locationTypeHint: metadata['location_type'],
    modalityHint: metadata['modality'],
    fallbackLocation: booking.location,
  });
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
  const sanitizedMeetingLocation = sanitizeMeetingLocation(booking.location);

  return {
    instructor_id: booking.instructorId,
    instructor_service_id: instructorServiceId,
    booking_date: bookingDate,
    start_time: booking.startTime,
    selected_duration: booking.duration,
    location_type: locationType,
    meeting_location: sanitizedMeetingLocation || getGenericMeetingLocationLabel(locationType),
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
