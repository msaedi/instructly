import * as Dialog from '@radix-ui/react-dialog';
import { ExternalLink, FileText, Mail, X } from 'lucide-react';

import { cn } from '@/lib/utils';
import { formatBookingDate, formatBookingTimeRange } from '@/lib/timezone/formatBookingTime';

import type { AdminBooking, BookingStatus } from '../hooks/useAdminBookings';
import { formatCurrency, formatDateTime } from '../utils';

interface BookingDetailPanelProps {
  booking: AdminBooking | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onIssueRefund: (booking: AdminBooking) => void;
  onViewAuditLog: (booking: AdminBooking) => void;
}

const timelineLabels: Record<string, string> = {
  booking_created: 'Booking created',
  payment_authorized: 'Payment authorized',
  lesson_started: 'Lesson started',
  lesson_completed: 'Lesson completed',
  payment_captured: 'Payment captured',
  lesson_no_show: 'Lesson marked no-show',
  refund_issued: 'Refund issued',
  booking_cancelled: 'Booking cancelled',
};

const statusStyles: Record<BookingStatus, string> = {
  CONFIRMED: 'bg-amber-100 text-amber-700',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  CANCELLED: 'bg-gray-200 text-gray-600',
  NO_SHOW: 'bg-rose-100 text-rose-700',
};

function StatusBadge({ value }: { value: BookingStatus }) {
  return (
    <span className={cn('inline-flex rounded-full px-2.5 py-1 text-xs font-semibold', statusStyles[value])}>
      {value}
    </span>
  );
}

export default function BookingDetailPanel({
  booking,
  open,
  onOpenChange,
  onIssueRefund,
  onViewAuditLog,
}: BookingDetailPanelProps) {
  const stripeUrl = booking?.payment_intent_id
    ? `https://dashboard.stripe.com/payments/${booking.payment_intent_id}`
    : null;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm" />
        <Dialog.Content className="fixed right-0 top-0 h-full w-full max-w-xl overflow-y-auto bg-white shadow-2xl">
          <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
            <div>
              <Dialog.Title className="text-lg font-semibold text-gray-900">Booking Details</Dialog.Title>
              {booking ? (
                <div className="mt-1 flex items-center gap-2">
                  <p className="text-xs text-gray-500">{booking.id}</p>
                  <StatusBadge value={booking.status} />
                </div>
              ) : null}
            </div>
            <Dialog.Close asChild>
              <button className="rounded-full p-2 text-gray-500 hover:bg-gray-100" aria-label="Close">
                <X className="h-4 w-4" />
              </button>
            </Dialog.Close>
          </div>

          {booking ? (
            <div className="space-y-6 p-6">
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <h3 className="text-sm font-semibold text-gray-700">Parties</h3>
                <div className="mt-3 grid gap-4 md:grid-cols-2">
                  <div>
                    <p className="text-xs text-gray-500">Student</p>
                    <p className="text-sm font-medium text-gray-900">{booking.student.name}</p>
                    <p className="text-xs text-gray-500">{booking.student.email}</p>
                  </div>
                  <div>
                    <p className="text-xs text-gray-500">Instructor</p>
                    <p className="text-sm font-medium text-gray-900">{booking.instructor.name}</p>
                    <p className="text-xs text-gray-500">{booking.instructor.email}</p>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-gray-700">Lesson</h3>
                <div className="mt-3 space-y-2 text-sm text-gray-700">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Service</span>
                    <span>{booking.service_name} ({booking.duration_minutes ?? 60} min)</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Date</span>
                    <span>{formatBookingDate(booking)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Time</span>
                    <span>{formatBookingTimeRange(booking)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Location</span>
                    <span>{booking.meeting_location ?? booking.location_type ?? '-'}</span>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-gray-700">Payment</h3>
                <div className="mt-3 space-y-2 text-sm text-gray-700">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Lesson Price</span>
                    <span>{formatCurrency(booking.lesson_price ?? booking.total_price)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Platform Fee</span>
                    <span>{formatCurrency(booking.platform_fee ?? 0)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Credits Applied</span>
                    <span>-{formatCurrency(booking.credits_applied ?? 0)}</span>
                  </div>
                  <div className="border-t border-gray-200 pt-2 flex items-center justify-between font-semibold">
                    <span>Total Charged</span>
                    <span>{formatCurrency(booking.total_price)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Payment Status</span>
                    <span className="capitalize">{booking.payment_status}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Payment Intent</span>
                    {stripeUrl ? (
                      <a
                        className="inline-flex items-center gap-1 text-indigo-600 hover:underline"
                        href={stripeUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {booking.payment_intent_id}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    ) : (
                      <span>-</span>
                    )}
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Instructor Payout</span>
                    <span>{formatCurrency(booking.instructor_payout ?? 0)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-500">Platform Revenue</span>
                    <span>{formatCurrency(booking.platform_revenue ?? 0)}</span>
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-4">
                <h3 className="text-sm font-semibold text-gray-700">Timeline</h3>
                <div className="mt-3 space-y-3 text-sm text-gray-600">
                  {(booking.timeline ?? []).map((item) => (
                    <div key={`${item.timestamp}-${item.event}`} className="flex items-start justify-between">
                      <div>
                        <div className="font-medium text-gray-800">{timelineLabels[item.event] ?? item.event}</div>
                        {item.amount ? (
                          <div className="text-xs text-gray-500">Amount: {formatCurrency(item.amount)}</div>
                        ) : null}
                      </div>
                      <div className="text-xs text-gray-400">{formatDateTime(item.timestamp)}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <h3 className="text-sm font-semibold text-gray-700">Actions</h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onIssueRefund(booking)}
                    className="inline-flex items-center rounded-full bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:brightness-110"
                  >
                    Issue Refund
                  </button>
                  <button
                    type="button"
                    className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium ring-1 ring-gray-300 hover:bg-white"
                  >
                    <Mail className="h-4 w-4" />
                    Contact
                  </button>
                  <button
                    type="button"
                    onClick={() => onViewAuditLog(booking)}
                    className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium ring-1 ring-gray-300 hover:bg-white"
                  >
                    <FileText className="h-4 w-4" />
                    Full Audit Log
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="p-6 text-sm text-gray-500">Select a booking to see details.</div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
