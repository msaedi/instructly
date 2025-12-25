/**
 * Format booking date/time fields for display in a viewer's timezone.
 *
 * Prefers UTC fields and falls back to legacy local date/time strings.
 */

type BookingTimeFields = {
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
