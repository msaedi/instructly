/**
 * Date/time and name formatting utilities
 */

import { formatDistanceToNow, format as formatDate } from 'date-fns';

/**
 * Format a date/time as relative time (e.g., "2 hours ago")
 */
export const formatRelativeTime = (input: string | Date | null | undefined): string => {
  if (!input) return '';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return '';
  return formatDistanceToNow(date, { addSuffix: true });
};

/**
 * Format a date/time as time label (e.g., "2:30 PM")
 */
export const formatTimeLabel = (input: string | Date | null | undefined): string => {
  if (!input) return '';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return '';
  return formatDate(date, 'p');
};

/**
 * Format a date as short date (e.g., "11/28/24")
 */
export const formatShortDate = (input: string | Date | null | undefined): string => {
  if (!input) return '';
  const date = typeof input === 'string' ? new Date(input) : input;
  if (Number.isNaN(date.getTime())) return '';
  return formatDate(date, 'MM/dd/yy');
};

/**
 * Get initials from first and last name
 */
export const getInitials = (firstName?: string | null, lastName?: string | null): string => {
  const first = (firstName?.[0] ?? '').toUpperCase();
  const last = (lastName?.[0] ?? '').toUpperCase();
  const combined = `${first}${last}`.trim();
  return combined || '??';
};

/**
 * Format student name with last initial (e.g., "John S.")
 */
export const formatStudentName = (firstName?: string | null, lastName?: string | null): string => {
  const first = firstName?.trim() ?? '';
  const lastInitial = lastName?.trim()?.[0];
  if (first && lastInitial) return `${first} ${lastInitial}.`;
  return first || lastName || 'Student';
};
