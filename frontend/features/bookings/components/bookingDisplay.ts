import { format } from 'date-fns';
import type { BookingStatus } from '@/features/shared/api/types';

export type BookingStatusDisplay = BookingStatus | 'IN_PROGRESS' | string | null | undefined;

const STATUS_LABELS: Record<string, string> = {
  PENDING: 'Pending',
  CONFIRMED: 'Confirmed',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'No-show',
  IN_PROGRESS: 'In Progress',
};

function parseBookingDateTime(date: string, time?: string): Date | null {
  const dateTime = new Date(time ? `${date}T${time}` : date);
  return Number.isNaN(dateTime.valueOf()) ? null : dateTime;
}

export function getBookingStatusLabel(status: BookingStatusDisplay): string {
  if (!status) {
    return 'Pending';
  }

  const normalized = String(status).toUpperCase();
  const label = STATUS_LABELS[normalized];
  if (label) {
    return label;
  }

  return normalized
    .toLowerCase()
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => `${part[0]?.toUpperCase() ?? ''}${part.slice(1)}`)
    .join(' ');
}

export function formatBookingCardDate(date: string, time: string): string {
  const parsed = parseBookingDateTime(date, time);
  return parsed ? format(parsed, 'EEE, MMM d') : date;
}

export function formatBookingLongDate(date: string, time: string): string {
  const parsed = parseBookingDateTime(date, time);
  return parsed ? format(parsed, 'EEEE, MMMM d') : date;
}

export function formatBookingCreatedDate(createdAt: string): string {
  const parsed = parseBookingDateTime(createdAt);
  return parsed ? format(parsed, 'M/d/yyyy') : createdAt;
}

export function formatBookingTimeRange(date: string, startTime: string, endTime: string): string {
  const start = parseBookingDateTime(date, startTime);
  const end = parseBookingDateTime(date, endTime);

  if (start && end) {
    return `${format(start, 'h:mm a')} – ${format(end, 'h:mm a')}`;
  }

  return `${startTime} – ${endTime}`;
}

export function formatDurationMinutes(durationMinutes: number): string {
  return `${durationMinutes} min`;
}

export function formatDurationWithService(durationMinutes: number, serviceName: string): string {
  return `${formatDurationMinutes(durationMinutes)} · ${serviceName}`;
}

export function formatPlainLabel(value: string): string {
  return value
    .toLowerCase()
    .split('_')
    .filter((part) => part.length > 0)
    .map((part) => `${part[0]?.toUpperCase() ?? ''}${part.slice(1)}`)
    .join(' ');
}
