import * as Popover from '@radix-ui/react-popover';
import { CheckCircle2, FileText, Mail, MoreVertical, UserRound, XCircle } from 'lucide-react';

import { cn } from '@/lib/utils';
import { formatBookingDate, formatBookingTimeRange } from '@/lib/timezone/formatBookingTime';
import { isRefundable } from '@/features/shared/types/paymentStatus';

import type { AdminBooking, BookingStatus, PaymentStatus } from '../hooks/useAdminBookings';
import { formatCurrency } from '../utils';

interface BookingsTableProps {
  bookings: AdminBooking[];
  total: number;
  page: number;
  perPage: number;
  totalPages: number;
  selectedIds: string[];
  onToggleSelect: (id: string) => void;
  onToggleSelectAll: (next: boolean) => void;
  onPageChange: (next: number) => void;
  onViewDetails: (booking: AdminBooking) => void;
  onIssueRefund: (booking: AdminBooking) => void;
  onCancelBooking: (booking: AdminBooking) => void;
  onContact: (booking: AdminBooking, target: 'student' | 'instructor') => void;
  onMarkStatus: (booking: AdminBooking, status: 'COMPLETED' | 'NO_SHOW') => void;
  onViewAuditLog: (booking: AdminBooking) => void;
}

const statusStyles: Record<BookingStatus, string> = {
  CONFIRMED: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
  COMPLETED: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
  CANCELLED: 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
  PAYMENT_FAILED: 'bg-amber-100 dark:bg-amber-900/30 text-amber-800 dark:text-amber-200',
  NO_SHOW: 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300',
};

const statusLabels: Record<BookingStatus, string> = {
  CONFIRMED: 'Confirmed',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  PAYMENT_FAILED: 'Payment Failed',
  NO_SHOW: 'No-show',
};

const paymentStyles: Record<PaymentStatus, string> = {
  scheduled: 'bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-indigo-200',
  authorized: 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-300',
  payment_method_required: 'bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-300',
  manual_review: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300',
  locked: 'bg-teal-100 dark:bg-teal-900/30 text-teal-700 dark:text-teal-300',
  settled: 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400',
};

const paymentLabels: Record<PaymentStatus, string> = {
  scheduled: 'Scheduled',
  authorized: 'Authorized',
  payment_method_required: 'Payment required',
  manual_review: 'Manual review',
  locked: 'Locked',
  settled: 'Settled',
};

function StatusBadge({ value }: { value: BookingStatus }) {
  return (
    <span className={cn('inline-flex rounded-full px-2.5 py-1 text-xs font-semibold', statusStyles[value])}>
      {statusLabels[value]}
    </span>
  );
}

function PaymentBadge({ value }: { value: PaymentStatus }) {
  return (
    <span className={cn('inline-flex rounded-full px-2.5 py-1 text-xs font-semibold', paymentStyles[value])}>
      {paymentLabels[value]}
    </span>
  );
}

function isLessonPast(booking: AdminBooking) {
  const bookingEndUtc = (booking as { booking_end_utc?: string | null }).booking_end_utc;
  const dateTime = bookingEndUtc
    ? new Date(bookingEndUtc)
    : new Date(`${booking.booking_date}T${booking.end_time}`);
  if (Number.isNaN(dateTime.getTime())) {
    return false;
  }
  return dateTime.getTime() <= Date.now();
}

export default function BookingsTable({
  bookings,
  total,
  page,
  perPage,
  totalPages,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  onPageChange,
  onViewDetails,
  onIssueRefund,
  onCancelBooking,
  onContact,
  onMarkStatus,
  onViewAuditLog,
}: BookingsTableProps) {
  const allSelected = bookings.length > 0 && bookings.every((booking) => selectedIds.includes(booking.id));
  const rangeStart = total === 0 ? 0 : (page - 1) * perPage + 1;
  const rangeEnd = Math.min(total, page * perPage);

  return (
    <div className="rounded-2xl bg-white/70 dark:bg-gray-900/50 ring-1 ring-gray-200/70 dark:ring-gray-700/60 shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
            <tr className="border-b border-gray-200/70 dark:border-gray-700/60">
              <th className="px-4 py-3 text-left">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(event) => onToggleSelectAll(event.target.checked)}
                />
              </th>
              <th className="px-4 py-3 text-left">ID</th>
              <th className="px-4 py-3 text-left">Student</th>
              <th className="px-4 py-3 text-left">Instructor</th>
              <th className="px-4 py-3 text-left">Date</th>
              <th className="px-4 py-3 text-left">Amount</th>
              <th className="px-4 py-3 text-left">Status</th>
              <th className="px-4 py-3 text-right"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-200/70 dark:divide-gray-700/60">
            {bookings.map((booking) => {
              const canRefund = isRefundable(booking.payment_status);
              const canMark = booking.status === 'CONFIRMED' && isLessonPast(booking);
              const canCancel = booking.status === 'CONFIRMED';
              return (
                <tr key={booking.id} className="hover:bg-gray-50/70 dark:hover:bg-gray-700/40">
                  <td className="px-4 py-4">
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(booking.id)}
                      onChange={() => onToggleSelect(booking.id)}
                    />
                  </td>
                  <td className="px-4 py-4">
                    <div className="font-medium text-gray-900 dark:text-gray-100">
                      {booking.id.slice(0, 8)}...
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{booking.service_name}</div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="font-medium text-gray-900 dark:text-gray-100">{booking.student.name}</div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="font-medium text-gray-900 dark:text-gray-100">{booking.instructor.name}</div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="text-gray-900 dark:text-gray-100">{formatBookingDate(booking)}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">{formatBookingTimeRange(booking)}</div>
                  </td>
                  <td className="px-4 py-4">
                    <div className="font-medium text-gray-900 dark:text-gray-100">{formatCurrency(booking.total_price)}</div>
                  </td>
                  <td className="px-4 py-4 space-y-2">
                    <StatusBadge value={booking.status} />
                    <PaymentBadge value={booking.payment_status} />
                  </td>
                  <td className="px-4 py-4 text-right">
                    <Popover.Root>
                      <Popover.Trigger asChild>
                        <button
                          type="button"
                          className="inline-flex h-8 w-8 items-center justify-center rounded-full text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
                          aria-label="Row actions"
                        >
                          <MoreVertical className="h-4 w-4" />
                        </button>
                      </Popover.Trigger>
                      <Popover.Portal>
                        <Popover.Content
                          align="end"
                          sideOffset={8}
                          className="w-56 rounded-xl bg-white dark:bg-gray-800 p-2 shadow-xl ring-1 ring-gray-200"
                        >
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                            onClick={() => onViewDetails(booking)}
                          >
                            <UserRound className="h-4 w-4" />
                            View Details
                          </button>
                          <button
                            type="button"
                            className={cn(
                              'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm',
                              canRefund ? 'text-indigo-700 hover:bg-indigo-50 dark:hover:bg-indigo-900/20' : 'text-gray-300 cursor-not-allowed'
                            )}
                            onClick={() => canRefund && onIssueRefund(booking)}
                          >
                            <CheckCircle2 className="h-4 w-4" />
                            Issue Refund
                          </button>
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                            onClick={() => onContact(booking, 'student')}
                          >
                            <Mail className="h-4 w-4" />
                            Contact Student
                          </button>
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                            onClick={() => onContact(booking, 'instructor')}
                          >
                            <Mail className="h-4 w-4" />
                            Contact Instructor
                          </button>
                          <div className="my-2 border-t border-gray-200 dark:border-gray-700" />
                          <button
                            type="button"
                            className={cn(
                              'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm',
                              canMark ? 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700' : 'text-gray-300 cursor-not-allowed'
                            )}
                            onClick={() => canMark && onMarkStatus(booking, 'COMPLETED')}
                          >
                            <CheckCircle2 className="h-4 w-4" />
                            Mark Complete
                          </button>
                          <button
                            type="button"
                            className={cn(
                              'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm',
                              canMark ? 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700' : 'text-gray-300 cursor-not-allowed'
                            )}
                            onClick={() => canMark && onMarkStatus(booking, 'NO_SHOW')}
                          >
                            <XCircle className="h-4 w-4" />
                            Mark No-Show
                          </button>
                          <button
                            type="button"
                            className={cn(
                              'flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm',
                              canCancel ? 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700' : 'text-gray-300 cursor-not-allowed'
                            )}
                            onClick={() => canCancel && onCancelBooking(booking)}
                          >
                            <XCircle className="h-4 w-4" />
                            Cancel Booking
                          </button>
                          <div className="my-2 border-t border-gray-200 dark:border-gray-700" />
                          <button
                            type="button"
                            className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
                            onClick={() => onViewAuditLog(booking)}
                          >
                            <FileText className="h-4 w-4" />
                            View Audit Log
                          </button>
                        </Popover.Content>
                      </Popover.Portal>
                    </Popover.Root>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
        <div>
          Showing {rangeStart}-{rangeEnd} of {total}
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, page - 1))}
            disabled={page <= 1}
            className="rounded-full px-3 py-1 text-xs font-medium ring-1 ring-gray-300 dark:ring-gray-700 disabled:opacity-40"
          >
            Prev
          </button>
          <span className="text-xs">Page {page} of {totalPages}</span>
          <button
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
            className="rounded-full px-3 py-1 text-xs font-medium ring-1 ring-gray-300 dark:ring-gray-700 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
