/**
 * Format booking date/time fields for display in a viewer's timezone.
 *
 * Prefers UTC fields and falls back to local date/time strings.
 */

import { timeToMinutes } from '@/lib/time';

export type BookingTimeFields = {
  booking_start_utc?: string | null;
  booking_end_utc?: string | null;
  booking_date?: string;
  start_time?: string;
  end_time?: string;
  lesson_timezone?: string | null;
};

const DEFAULT_LOCALE = 'en-US';

const getViewerTimezone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone;

export function formatBookingTime(
  booking: BookingTimeFields,
  viewerTimezone: string = getViewerTimezone(),
  options: Intl.DateTimeFormatOptions = {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }
): string {
  if (booking.booking_start_utc) {
    const utcDate = new Date(booking.booking_start_utc);
    if (!Number.isNaN(utcDate.getTime())) {
      return utcDate.toLocaleTimeString(DEFAULT_LOCALE, {
        ...options,
        timeZone: viewerTimezone,
      });
    }
  }

  if (booking.booking_date && booking.start_time) {
    const dateTimeStr = `${booking.booking_date}T${booking.start_time}`;
    const date = new Date(dateTimeStr);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleTimeString(DEFAULT_LOCALE, options);
    }
  }

  return 'Time unavailable';
}

export function formatBookingDate(
  booking: Pick<BookingTimeFields, 'booking_start_utc' | 'booking_date'>,
  viewerTimezone: string = getViewerTimezone(),
  options: Intl.DateTimeFormatOptions = {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  }
): string {
  if (booking.booking_start_utc) {
    const utcDate = new Date(booking.booking_start_utc);
    if (!Number.isNaN(utcDate.getTime())) {
      return utcDate.toLocaleDateString(DEFAULT_LOCALE, {
        ...options,
        timeZone: viewerTimezone,
      });
    }
  }

  if (booking.booking_date) {
    const date = new Date(`${booking.booking_date}T00:00:00`);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleDateString(DEFAULT_LOCALE, options);
    }
  }

  return 'Date unavailable';
}

export function formatBookingDateTime(
  booking: BookingTimeFields,
  viewerTimezone: string = getViewerTimezone()
): string {
  const date = formatBookingDate(booking, viewerTimezone);
  const time = formatBookingTime(booking, viewerTimezone);

  const timeParts = new Intl.DateTimeFormat(DEFAULT_LOCALE, {
    timeZone: viewerTimezone,
    timeZoneName: 'short',
  }).formatToParts(new Date());
  const tzName = timeParts.find((part) => part.type === 'timeZoneName')?.value;

  return tzName ? `${date} at ${time} ${tzName}` : `${date} at ${time}`;
}

export function formatBookingTimeRange(
  booking: BookingTimeFields,
  viewerTimezone: string = getViewerTimezone(),
  options?: Intl.DateTimeFormatOptions
): string {
  const start = formatBookingTime(booking, viewerTimezone, options);
  let end = 'Time unavailable';
  if (booking.booking_end_utc) {
    end = formatBookingTime(
      { booking_start_utc: booking.booking_end_utc },
      viewerTimezone,
      options
    );
  } else if (booking.booking_date && booking.end_time) {
    end = formatBookingTime(
      {
        booking_date: booking.booking_date,
        start_time: booking.end_time,
        lesson_timezone: booking.lesson_timezone ?? null,
      },
      viewerTimezone,
      options
    );
  }

  if (start === 'Time unavailable' || end === 'Time unavailable') {
    return 'Time unavailable';
  }

  return `${start} - ${end}`;
}

function buildLocalDateTime(date: string, time: string): Date | null {
  const value = new Date(`${date}T${time}`);
  return Number.isNaN(value.getTime()) ? null : value;
}

export function resolveBookingDateTimes(
  booking: BookingTimeFields & { duration_minutes?: number | null }
): { start: Date | null; end: Date | null } {
  if (booking.booking_start_utc) {
    const startUtc = new Date(booking.booking_start_utc);
    if (!Number.isNaN(startUtc.getTime())) {
      let endUtc: Date | null = null;
      if (booking.booking_end_utc) {
        const candidate = new Date(booking.booking_end_utc);
        endUtc = Number.isNaN(candidate.getTime()) ? null : candidate;
      } else if (
        typeof booking.duration_minutes === 'number' &&
        Number.isFinite(booking.duration_minutes)
      ) {
        endUtc = new Date(startUtc.getTime() + booking.duration_minutes * 60 * 1000);
      }
      return { start: startUtc, end: endUtc };
    }
  }

  if (booking.booking_date && booking.start_time) {
    const startLocal = buildLocalDateTime(booking.booking_date, booking.start_time);
    if (!startLocal) {
      return { start: null, end: null };
    }

    let endLocal: Date | null = null;
    if (booking.end_time) {
      const startMinutes = timeToMinutes(booking.start_time);
      const endMinutes = timeToMinutes(booking.end_time, { isEndTime: true });
      endLocal = new Date(startLocal);

      if (endMinutes === 24 * 60) {
        endLocal.setDate(endLocal.getDate() + 1);
        endLocal.setHours(0, 0, 0, 0);
      } else {
        if (endMinutes <= startMinutes) {
          endLocal.setDate(endLocal.getDate() + 1);
        }
        endLocal.setHours(Math.floor(endMinutes / 60), endMinutes % 60, 0, 0);
      }
    } else if (
      typeof booking.duration_minutes === 'number' &&
      Number.isFinite(booking.duration_minutes)
    ) {
      endLocal = new Date(startLocal.getTime() + booking.duration_minutes * 60 * 1000);
    }

    return { start: startLocal, end: endLocal };
  }

  return { start: null, end: null };
}
