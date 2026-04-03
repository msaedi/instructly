import type { BookingStatus } from '@/features/shared/api/types';
import { resolveBookingDateTimes } from '@/lib/timezone/formatBookingTime';
import type { BookingStatusDisplay } from './bookingDisplay';

type InstructorBookingDisplayStatusSource = {
  status?: BookingStatus | string | null;
  booking_date: string;
  start_time: string;
  end_time: string;
  lesson_timezone?: string | null;
  duration_minutes?: number | null;
  booking_start_utc?: string | null;
  booking_end_utc?: string | null;
};

export function getInstructorBookingEndTime(
  booking: InstructorBookingDisplayStatusSource
): Date | null {
  const { end } = resolveBookingDateTimes(booking);
  if (end === null || Number.isNaN(end.getTime())) {
    return null;
  }

  return end;
}

export function getInstructorBookingDisplayStatus(
  booking: InstructorBookingDisplayStatusSource,
  now: Date = new Date()
): BookingStatusDisplay {
  if (String(booking.status).toUpperCase() !== 'CONFIRMED') {
    return booking.status;
  }

  const { start, end } = resolveBookingDateTimes(booking);
  if (start === null || end === null) {
    return booking.status;
  }

  return now >= start && now < end ? 'IN_PROGRESS' : booking.status;
}
