import type { BookingStatus } from '../hooks/useAdminBookings';

export const bookingStatusStyles: Record<BookingStatus, string> = {
  PENDING: 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200',
  CONFIRMED: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
  COMPLETED: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
  CANCELLED: 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
  PAYMENT_FAILED: 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200',
  NO_SHOW: 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300',
};

export const bookingStatusLabels: Record<BookingStatus, string> = {
  PENDING: 'Pending',
  CONFIRMED: 'Confirmed',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  PAYMENT_FAILED: 'Payment Failed',
  NO_SHOW: 'No-show',
};
