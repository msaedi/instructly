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
const zonedFormatterCache = new Map<string, Intl.DateTimeFormat>();

const getViewerTimezone = (): string => Intl.DateTimeFormat().resolvedOptions().timeZone;

function getZonedFormatter(timeZone: string): Intl.DateTimeFormat {
  let formatter = zonedFormatterCache.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(DEFAULT_LOCALE, {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
    zonedFormatterCache.set(timeZone, formatter);
  }
  return formatter;
}

function parseDateParts(value: string): { year: number; month: number; day: number } | null {
  const [yearRaw, monthRaw, dayRaw] = value.split('-');
  const year = Number.parseInt(yearRaw ?? '', 10);
  const month = Number.parseInt(monthRaw ?? '', 10);
  const day = Number.parseInt(dayRaw ?? '', 10);

  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
    return null;
  }

  return { year, month, day };
}

function parseTimeParts(value: string): { hour: number; minute: number; second: number } | null {
  const [hourRaw, minuteRaw = '0', secondRaw = '0'] = value.split(':');
  const hour = Number.parseInt(hourRaw ?? '', 10);
  const minute = Number.parseInt(minuteRaw ?? '', 10);
  const second = Number.parseInt(secondRaw ?? '', 10);

  if (!Number.isFinite(hour) || !Number.isFinite(minute) || !Number.isFinite(second)) {
    return null;
  }

  return { hour, minute, second };
}

function partsToObject(parts: Intl.DateTimeFormatPart[]): {
  year: number;
  month: number;
  day: number;
  hour: number;
  minute: number;
  second: number;
} {
  const out = {
    year: 0,
    month: 0,
    day: 0,
    hour: 0,
    minute: 0,
    second: 0,
  };

  for (const part of parts) {
    if (part.type === 'literal') {
      continue;
    }

    switch (part.type) {
      case 'year':
        out.year = Number(part.value);
        break;
      case 'month':
        out.month = Number(part.value);
        break;
      case 'day':
        out.day = Number(part.value);
        break;
      case 'hour':
        out.hour = Number(part.value);
        break;
      case 'minute':
        out.minute = Number(part.value);
        break;
      case 'second':
        out.second = Number(part.value);
        break;
      default:
        break;
    }
  }

  return out;
}

function compareLocalDateTimes(
  actual: { year: number; month: number; day: number; hour: number; minute: number; second: number },
  desired: { year: number; month: number; day: number; hour: number; minute: number; second: number }
): number {
  const actualMinutes =
    Date.UTC(
      actual.year,
      actual.month - 1,
      actual.day,
      actual.hour,
      actual.minute,
      actual.second,
    ) / 60000;
  const desiredMinutes =
    Date.UTC(
      desired.year,
      desired.month - 1,
      desired.day,
      desired.hour,
      desired.minute,
      desired.second,
    ) / 60000;

  return desiredMinutes - actualMinutes;
}

function addDays(date: string, days: number): string {
  const parts = parseDateParts(date);
  if (!parts) {
    return date;
  }

  const utc = Date.UTC(parts.year, parts.month - 1, parts.day);
  const adjusted = new Date(utc + days * 24 * 60 * 60 * 1000);
  const year = adjusted.getUTCFullYear();
  const month = String(adjusted.getUTCMonth() + 1).padStart(2, '0');
  const day = String(adjusted.getUTCDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function buildZonedDateTime(date: string, time: string, timeZone: string): Date | null {
  const dateParts = parseDateParts(date);
  const timeParts = parseTimeParts(time);

  if (!dateParts || !timeParts) {
    return null;
  }

  const desired = {
    year: dateParts.year,
    month: dateParts.month,
    day: dateParts.day,
    hour: timeParts.hour,
    minute: timeParts.minute,
    second: timeParts.second,
  };

  let instant = Date.UTC(
    desired.year,
    desired.month - 1,
    desired.day,
    desired.hour,
    desired.minute,
    desired.second,
  );
  let iterations = 0;
  let previousDiff = Number.NaN;

  while (iterations < 8) {
    const actual = partsToObject(getZonedFormatter(timeZone).formatToParts(new Date(instant)));
    const diffMinutes = compareLocalDateTimes(actual, desired);

    if (diffMinutes === 0) {
      return new Date(instant);
    }

    if (!Number.isNaN(previousDiff) && Math.abs(diffMinutes) === Math.abs(previousDiff)) {
      break;
    }

    previousDiff = diffMinutes;
    instant += diffMinutes * 60000;
    iterations += 1;
  }

  return new Date(instant);
}

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
    if (booking.lesson_timezone) {
      const startZoned = buildZonedDateTime(
        booking.booking_date,
        booking.start_time,
        booking.lesson_timezone,
      );
      if (!startZoned) {
        return { start: null, end: null };
      }

      let endZoned: Date | null = null;
      if (booking.end_time) {
        const startMinutes = timeToMinutes(booking.start_time);
        const endMinutes = timeToMinutes(booking.end_time, { isEndTime: true });
        let endDate = booking.booking_date;
        let normalizedEndTime = booking.end_time;

        if (endMinutes === 24 * 60) {
          endDate = addDays(booking.booking_date, 1);
          normalizedEndTime = '00:00:00';
        }

        endZoned = buildZonedDateTime(endDate, normalizedEndTime, booking.lesson_timezone);

        if (endZoned && endMinutes !== 24 * 60 && endMinutes <= startMinutes) {
          endZoned = buildZonedDateTime(
            addDays(endDate, 1),
            normalizedEndTime,
            booking.lesson_timezone,
          );
        }
      } else if (
        typeof booking.duration_minutes === 'number' &&
        Number.isFinite(booking.duration_minutes)
      ) {
        endZoned = new Date(startZoned.getTime() + booking.duration_minutes * 60 * 1000);
      }

      return { start: startZoned, end: endZoned };
    }

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
