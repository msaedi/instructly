import { toDateOnlyString } from '@/lib/availability/dateHelpers';
import { addMinutesHHMM, to24HourTime } from '@/lib/time';
import type { CreateBookingRequest } from '@/features/shared/api/client';
import type { BookingPayment } from '../types';

interface BuildCreateBookingPayloadParams {
  instructorId: string;
  serviceId: string;
  bookingDate: string | Date;
  instructorTimezone?: string;
  booking: BookingPayment & {
    metadata?: Record<string, unknown>;
  };
}

function normalizeDuration(value: unknown, startTime?: string, endTime?: string): number {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return Math.round(value);
  }
  const numericFromString = typeof value === 'string' ? Number(value) : NaN;
  if (Number.isFinite(numericFromString) && numericFromString > 0) {
    return Math.round(numericFromString);
  }
  if (startTime && endTime) {
    const start = to24HourTime(startTime);
    const end = to24HourTime(endTime);
    const [shRaw = '0', smRaw = '0'] = start.split(':');
    const [ehRaw = '0', emRaw = '0'] = end.split(':');
    const sh = parseInt(shRaw, 10);
    const sm = parseInt(smRaw, 10);
    const eh = parseInt(ehRaw, 10);
    const em = parseInt(emRaw, 10);
    const diff = eh * 60 + em - (sh * 60 + sm);
    if (Number.isFinite(diff) && diff > 0) {
      return diff;
    }
  }
  throw new Error('Unable to determine selected duration for booking payload');
}

function normalizeBookingDate(value: string | Date): string {
  if (value instanceof Date) {
    return toDateOnlyString(value, 'booking.date');
  }
  return toDateOnlyString(value, 'booking.date');
}

function normalizeTimezone(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : undefined;
}

type NormalizedLocationType =
  | 'student_location'
  | 'instructor_location'
  | 'online'
  | 'neutral_location';

function normalizeLocationType(
  modality: unknown,
  fallbackLocation: string | undefined,
): NormalizedLocationType {
  const raw = typeof modality === 'string' ? modality.toLowerCase() : '';
  if (raw.includes('remote') || raw.includes('online') || raw.includes('virtual')) {
    return 'online';
  }
  if (raw.includes('instructor') || raw.includes('studio')) {
    return 'instructor_location';
  }
  if (raw.includes('neutral') || raw.includes('public')) {
    return 'neutral_location';
  }
  const fallback = typeof fallbackLocation === 'string' ? fallbackLocation.toLowerCase() : '';
  if (fallback.includes('remote') || fallback.includes('online') || fallback.includes('virtual')) {
    return 'online';
  }
  return 'student_location';
}

/**
 * Build the payload expected by POST /bookings/ using the booking selection state.
 */
export function buildCreateBookingPayload({
  instructorId,
  serviceId,
  bookingDate,
  instructorTimezone,
  booking,
}: BuildCreateBookingPayloadParams): CreateBookingRequest {
  if (!booking.startTime || !booking.endTime) {
    throw new Error('Booking start and end times are required to build payload');
  }

  const metadata = booking.metadata ?? {};
  const startTime24h = to24HourTime(String(booking.startTime));
  const durationMinutes = normalizeDuration(
    booking.duration ??
      (typeof metadata['duration'] === 'number' ? metadata['duration'] : undefined) ??
      (typeof metadata['duration_minutes'] === 'number' ? metadata['duration_minutes'] : undefined) ??
      (typeof metadata['durationMinutes'] === 'number' ? metadata['durationMinutes'] : undefined),
    booking.startTime,
    booking.endTime,
  );
  const locationType = normalizeLocationType(metadata['modality'], booking.location);
  const meetingLocation = booking.location || (locationType === 'online' ? 'Online' : 'In-person lesson');
  const normalizedDate = normalizeBookingDate(bookingDate);
  const resolvedTimezone =
    normalizeTimezone(instructorTimezone) ??
    normalizeTimezone(metadata['timezone']) ??
    normalizeTimezone(metadata['lesson_timezone']) ??
    normalizeTimezone(metadata['lessonTimezone']) ??
    normalizeTimezone(metadata['instructor_timezone']) ??
    normalizeTimezone(metadata['instructorTimezone']);

  const payload: CreateBookingRequest = {
    instructor_id: instructorId,
    instructor_service_id: serviceId,
    booking_date: normalizedDate,
    start_time: startTime24h,
    end_time: addMinutesHHMM(startTime24h, durationMinutes),
    selected_duration: durationMinutes,
    meeting_location: meetingLocation,
    location_type: locationType,
  };

  if (resolvedTimezone) {
    payload.timezone = resolvedTimezone;
  }

  return payload;
}
