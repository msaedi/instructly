import { toDateOnlyString } from '@/lib/availability/dateHelpers';
import { addMinutesHHMM, to24HourTime } from '@/lib/time';
import type { AvailabilityCheckRequest } from '@/src/api/generated/instructly.schemas';
import type { BookingPayment } from '../types';
import { resolveLocationType, sanitizeMeetingLocation } from './locationUtils';

export type AvailabilityCheckBooking = BookingPayment & {
  metadata?: Record<string, unknown>;
  serviceId?: string;
};

type BuildAvailabilityCheckRequestParams = {
  bookingCandidate: AvailabilityCheckBooking;
  updatedBookingData: AvailabilityCheckBooking;
  bookingData: AvailabilityCheckBooking;
};

function normalizeNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

export function buildAvailabilityCheckRequest({
  bookingCandidate,
  updatedBookingData,
  bookingData,
}: BuildAvailabilityCheckRequestParams): AvailabilityCheckRequest | null {
  const instructorCandidate =
    bookingCandidate.instructorId ?? updatedBookingData.instructorId ?? bookingData.instructorId;
  const instructorId =
    typeof instructorCandidate === 'string'
      ? instructorCandidate
      : instructorCandidate != null
        ? String(instructorCandidate)
        : '';
  if (!instructorId) {
    return null;
  }

  const metadata = {
    ...(bookingData.metadata ?? {}),
    ...(updatedBookingData.metadata ?? {}),
    ...(bookingCandidate.metadata ?? {}),
  } as Record<string, unknown>;

  const serviceCandidate =
    metadata['serviceId'] ??
    bookingCandidate.serviceId ??
    updatedBookingData.serviceId ??
    bookingData.serviceId ??
    null;
  const instructorServiceId =
    serviceCandidate == null
      ? ''
      : typeof serviceCandidate === 'string'
        ? serviceCandidate
        : String(serviceCandidate);
  if (!instructorServiceId) {
    return null;
  }

  const bookingDateSource = bookingCandidate.date ?? updatedBookingData.date ?? bookingData.date;
  if (!bookingDateSource) {
    return null;
  }

  let bookingDateLocal: string;
  try {
    bookingDateLocal = toDateOnlyString(bookingDateSource, 'availability-check.booking-date');
  } catch {
    return null;
  }

  const startTimeSource =
    bookingCandidate.startTime ?? updatedBookingData.startTime ?? bookingData.startTime;
  if (!startTimeSource) {
    return null;
  }

  let startTime24h: string;
  try {
    startTime24h = to24HourTime(String(startTimeSource));
  } catch {
    return null;
  }

  const durationCandidates = [
    bookingCandidate.duration,
    updatedBookingData.duration,
    bookingData.duration,
    metadata['duration'],
    metadata['duration_minutes'],
  ];
  let selectedDuration: number | null = null;
  for (const candidate of durationCandidates) {
    if (typeof candidate === 'number' && Number.isFinite(candidate) && candidate > 0) {
      selectedDuration = Math.round(candidate);
      break;
    }
    if (typeof candidate === 'string') {
      const parsed = Number(candidate);
      if (Number.isFinite(parsed) && parsed > 0) {
        selectedDuration = Math.round(parsed);
        break;
      }
    }
  }
  if (!selectedDuration) {
    return null;
  }

  const endTimeSource =
    bookingCandidate.endTime ?? updatedBookingData.endTime ?? bookingData.endTime;
  let endTime24h = addMinutesHHMM(startTime24h, selectedDuration);
  if (endTimeSource) {
    try {
      endTime24h = to24HourTime(String(endTimeSource));
    } catch {
      endTime24h = addMinutesHHMM(startTime24h, selectedDuration);
    }
  }

  const fallbackLocation =
    sanitizeMeetingLocation(bookingCandidate.location) ||
    sanitizeMeetingLocation(updatedBookingData.location) ||
    sanitizeMeetingLocation(bookingData.location);
  const locationType = resolveLocationType({
    locationTypeHint: metadata['location_type'],
    modalityHint: metadata['modality'],
    fallbackLocation,
  });
  const locationAddress =
    locationType === 'online'
      ? undefined
      : sanitizeMeetingLocation(bookingCandidate.address?.fullAddress) ||
        sanitizeMeetingLocation(updatedBookingData.address?.fullAddress) ||
        sanitizeMeetingLocation(bookingData.address?.fullAddress) ||
        sanitizeMeetingLocation(metadata['location_address']) ||
        fallbackLocation ||
        undefined;
  const locationPlaceId =
    locationType === 'online'
      ? undefined
      : (typeof bookingCandidate.address?.placeId === 'string'
          ? bookingCandidate.address.placeId
          : undefined) ||
        (typeof updatedBookingData.address?.placeId === 'string'
          ? updatedBookingData.address.placeId
          : undefined) ||
        (typeof bookingData.address?.placeId === 'string'
          ? bookingData.address.placeId
          : undefined) ||
        (typeof metadata['location_place_id'] === 'string'
          ? metadata['location_place_id']
          : undefined) ||
        (typeof metadata['place_id'] === 'string' ? metadata['place_id'] : undefined);
  const locationLat =
    locationType === 'online'
      ? undefined
      : (normalizeNumber(bookingCandidate.address?.lat) ??
        normalizeNumber(updatedBookingData.address?.lat) ??
        normalizeNumber(bookingData.address?.lat) ??
        normalizeNumber(metadata['location_lat']));
  const locationLng =
    locationType === 'online'
      ? undefined
      : (normalizeNumber(bookingCandidate.address?.lng) ??
        normalizeNumber(updatedBookingData.address?.lng) ??
        normalizeNumber(bookingData.address?.lng) ??
        normalizeNumber(metadata['location_lng']));

  const bookingIdCandidate =
    (typeof bookingCandidate.bookingId === 'string' && bookingCandidate.bookingId.trim()) ||
    (typeof updatedBookingData.bookingId === 'string' && updatedBookingData.bookingId.trim()) ||
    (typeof bookingData.bookingId === 'string' && bookingData.bookingId.trim()) ||
    '';

  return {
    instructor_id: instructorId,
    instructor_service_id: instructorServiceId,
    booking_date: bookingDateLocal,
    start_time: startTime24h,
    end_time: endTime24h,
    location_type: locationType,
    selected_duration: selectedDuration,
    ...(locationAddress !== undefined ? { location_address: locationAddress } : {}),
    ...(locationPlaceId !== undefined ? { location_place_id: locationPlaceId } : {}),
    ...(locationLat !== undefined ? { location_lat: locationLat } : {}),
    ...(locationLng !== undefined ? { location_lng: locationLng } : {}),
    ...(bookingIdCandidate ? { exclude_booking_id: bookingIdCandidate } : {}),
  };
}
