import { format, parseISO } from 'date-fns';
import type { ConversationBooking } from '../types';

type BookingDateTime = {
  date?: string | null;
  start_time?: string | null;
};

type BookingStatusLike = {
  status?: string | null;
};

export function formatDateShort(dateStr?: string | null): string {
  if (!dateStr) {
    return '';
  }

  try {
    const date = parseISO(dateStr);
    return format(date, 'MMM d');
  } catch {
    return dateStr;
  }
}

export function formatTime12h(timeStr?: string | null): string {
  if (!timeStr) {
    return '';
  }

  const [hoursStr, minutesStr] = timeStr.split(':');
  const hours = parseInt(hoursStr ?? '0', 10);
  const minutes = parseInt(minutesStr ?? '0', 10);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes) || !minutesStr) {
    return timeStr;
  }

  const period = hours < 12 ? 'am' : 'pm';
  let hour12 = hours % 12;
  if (hour12 === 0) {
    hour12 = 12;
  }

  if (minutes === 0) {
    return `${hour12}${period}`;
  }

  return `${hour12}:${minutesStr}${period}`;
}

export function formatBookingInfo(
  booking: Pick<ConversationBooking, 'service_name' | 'date' | 'start_time'>
): string {
  const rawDate = booking.date ?? '';
  const rawTime = booking.start_time ?? '';
  const formattedDate = formatDateShort(rawDate);
  const formattedTime = formatTime12h(rawTime);

  return formattedDate === rawDate && formattedTime === rawTime
    ? `${booking.service_name} - ${rawDate}`
    : `${booking.service_name} on ${formattedDate}, ${formattedTime}`;
}

export function formatBookingDateTime(
  booking: Pick<ConversationBooking, 'date' | 'start_time'>
): string {
  return `${formatDateShort(booking.date)}, ${formatTime12h(booking.start_time)}`;
}

export function getBookingTimestamp(
  booking: BookingDateTime,
  fallback = 0
): number {
  const date = booking.date ?? '';
  const startTime = booking.start_time ?? '';
  const parsed = Date.parse(`${date}T${startTime}`);

  if (Number.isFinite(parsed)) {
    return parsed;
  }

  const fallbackParsed = Date.parse(date);
  return Number.isFinite(fallbackParsed) ? fallbackParsed : fallback;
}

export function getExplicitBookingStatus(booking: BookingStatusLike): string | null {
  return typeof booking.status === 'string' && booking.status.trim()
    ? booking.status.trim().toUpperCase()
    : null;
}

export function getBookingStatus(
  booking: Pick<ConversationBooking, 'date' | 'start_time' | 'status'>,
  nowTimestamp: number
): string {
  const explicitStatus = getExplicitBookingStatus(booking);
  if (explicitStatus) {
    return explicitStatus;
  }

  return getBookingTimestamp(booking, Number.POSITIVE_INFINITY) < nowTimestamp
    ? 'COMPLETED'
    : 'CONFIRMED';
}

export function getBookingStatusLabel(status: string): string {
  switch (status) {
    case 'CONFIRMED':
      return 'Confirmed';
    case 'COMPLETED':
      return 'Completed';
    case 'CANCELLED':
      return 'Cancelled';
    case 'NO_SHOW':
      return 'No Show';
    case 'IN_PROGRESS':
      return 'In Progress';
    default:
      return status
        .toLowerCase()
        .split('_')
        .filter(Boolean)
        .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
        .join(' ');
  }
}
