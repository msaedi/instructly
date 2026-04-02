export const CONFIRMED_BOOKING_BADGE_CLASSES =
  'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300';
export const COMPLETED_BOOKING_BADGE_CLASSES =
  'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-200';
export const CANCELLED_BOOKING_BADGE_CLASSES =
  'bg-rose-50 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300';
export const PAYMENT_FAILED_BOOKING_BADGE_CLASSES =
  'bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200';
export const NO_SHOW_BOOKING_BADGE_CLASSES =
  'bg-amber-50 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200';
export const IN_PROGRESS_BOOKING_BADGE_CLASSES =
  'bg-purple-50 dark:bg-purple-900/40 text-purple-700 dark:text-purple-200';
export const DEFAULT_BOOKING_BADGE_CLASSES =
  'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300';

export function getBookingStatusBadgeClasses(status?: string | null): string {
  switch (status?.toUpperCase()) {
    case 'UPCOMING':
    case 'CONFIRMED':
      return CONFIRMED_BOOKING_BADGE_CLASSES;
    case 'COMPLETED':
      return COMPLETED_BOOKING_BADGE_CLASSES;
    case 'CANCELLED':
      return CANCELLED_BOOKING_BADGE_CLASSES;
    case 'PAYMENT_FAILED':
      return PAYMENT_FAILED_BOOKING_BADGE_CLASSES;
    case 'NO_SHOW':
      return NO_SHOW_BOOKING_BADGE_CLASSES;
    case 'IN_PROGRESS':
      return IN_PROGRESS_BOOKING_BADGE_CLASSES;
    default:
      return DEFAULT_BOOKING_BADGE_CLASSES;
  }
}
