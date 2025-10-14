import { toDateOnlyString } from '@/lib/availability/dateHelpers';
import { addMinutesHHMM, to24HourTime } from '@/lib/time';
import type { CreateBookingRequest } from '@/features/shared/api/client';
import type { BookingPayment } from '../types';

interface BuildCreateBookingPayloadParams {
  instructorId: string;
  serviceId: string;
  bookingDate: string | Date;
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

function normalizeModality(modality: unknown, fallbackLocation: string | undefined): 'remote' | 'in_person' {
  const raw = typeof modality === 'string' ? modality.toLowerCase() : '';
  if (raw.includes('remote') || raw.includes('online') || raw.includes('virtual')) {
    return 'remote';
  }
  if (raw.includes('in_person') || raw.includes('in-person')) {
    return 'in_person';
  }
  const fallback = typeof fallbackLocation === 'string' ? fallbackLocation.toLowerCase() : '';
  if (fallback.includes('online') || fallback.includes('remote') || fallback.includes('virtual')) {
    return 'remote';
  }
  return 'in_person';
}

/**
 * Build the payload expected by POST /bookings/ using the booking selection state.
 */
export function buildCreateBookingPayload({
  instructorId,
  serviceId,
  bookingDate,
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
  const modality = normalizeModality(metadata['modality'], booking.location);
  const meetingLocation = booking.location || (modality === 'remote' ? 'Online' : 'In-person lesson');
  const normalizedDate = normalizeBookingDate(bookingDate);
  const locationType = modality;

  return {
    instructor_id: instructorId,
    instructor_service_id: serviceId,
    booking_date: normalizedDate,
    start_time: startTime24h,
    end_time: addMinutesHHMM(startTime24h, durationMinutes),
    selected_duration: durationMinutes,
    meeting_location: meetingLocation,
    location_type: locationType,
  };
}
