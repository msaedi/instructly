import { formatDistanceToNow } from 'date-fns';

/**
 * Format a date/time as relative time (e.g., "just now", "2 minutes ago")
 * Shared across student and instructor message views.
 */
export function formatRelativeTimestamp(input: string | Date | null | undefined): string {
  if (!input) return '';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return '';
  return formatDistanceToNow(date, { addSuffix: true });
}
