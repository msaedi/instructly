import { Card } from '@/components/ui/card';
import { format } from 'date-fns';
import { AlertTriangle, CalendarDays, CheckCircle, ChevronRight, Clock, User } from 'lucide-react';
import { Fragment } from 'react';
import { JoinLessonButton } from '@/components/lessons/video/JoinLessonButton';

export type BookingListItem = {
  id: string;
  booking_date: string;
  start_time: string;
  end_time?: string;
  status: string;
  service_name: string;
  total_price?: number | null;
  student?: {
    first_name?: string | null;
    last_name?: string | null;
  };
  instructor?: {
    first_name?: string | null;
    last_initial?: string | null;
  };
  join_opens_at?: string | null;
  join_closes_at?: string | null;
};

type BookingListProps = {
  data: BookingListItem[];
  isLoading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  'data-testid'?: string;
  /** Optional callback when a booking card is clicked to view details */
  onViewDetails?: (bookingId: string) => void;
  /** Optional callback when "Mark Complete" is clicked on a past CONFIRMED booking */
  onComplete?: (bookingId: string) => void;
  /** Optional callback when "Report No-Show" is clicked on a past CONFIRMED booking */
  onNoShow?: (bookingId: string) => void;
  /** Whether an action is currently pending (disables buttons) */
  isActionPending?: boolean;
};

const STATUS_LABELS: Record<string, string> = {
  CONFIRMED: 'Confirmed',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'No-show',
  IN_PROGRESS: 'In Progress',
};

const STATUS_STYLES: Record<string, string> = {
  CONFIRMED: 'bg-emerald-50 text-emerald-700',
  COMPLETED: 'bg-blue-50 text-blue-700',
  CANCELLED: 'bg-rose-50 text-rose-700',
  NO_SHOW: 'bg-amber-50 text-amber-800',
  IN_PROGRESS: 'bg-purple-50 text-purple-700',
};

/**
 * Check if a booking is currently in progress (lesson has started but not ended).
 */
function isInProgress(booking: BookingListItem): boolean {
  if (booking.status !== 'CONFIRMED' || !booking.end_time) return false;
  const now = new Date();
  const start = new Date(`${booking.booking_date}T${booking.start_time}`);
  const end = new Date(`${booking.booking_date}T${booking.end_time}`);
  return now >= start && now < end;
}

/**
 * Check if a booking is past and needs action (CONFIRMED but lesson has ended).
 */
function needsAction(booking: BookingListItem): boolean {
  if (booking.status !== 'CONFIRMED' || !booking.end_time) return false;
  const end = new Date(`${booking.booking_date}T${booking.end_time}`);
  return end < new Date();
}

function formatLessonDate(date: string, time: string): { date: string; time: string } {
  const start = new Date(`${date}T${time}`);
  if (Number.isNaN(start.valueOf())) {
    return { date, time };
  }
  return {
    date: format(start, 'EEE, MMM d'),
    time: format(start, 'h:mm a'),
  };
}

export function BookingList({
  data,
  isLoading,
  emptyDescription,
  emptyTitle,
  'data-testid': dataTestId = 'booking-list',
  onViewDetails,
  onComplete,
  onNoShow,
  isActionPending = false,
}: BookingListProps) {
  if (isLoading) {
    return (
      <div className="space-y-3" data-testid={`${dataTestId}-loading`}>
        {Array.from({ length: 2 }).map((_, idx) => (
          <Card
            key={`booking-skeleton-${idx}`}
            className="animate-pulse rounded-xl border border-gray-200 bg-white p-4"
          >
            <div className="h-4 w-1/3 rounded bg-gray-200" />
            <div className="mt-2 h-4 w-1/4 rounded bg-gray-100" />
            <div className="mt-4 h-3 w-1/5 rounded bg-gray-100" />
          </Card>
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div
        className="rounded-xl border border-dashed border-gray-300 bg-white p-6 text-center"
        data-testid={`${dataTestId}-empty`}
      >
        <p className="text-base font-semibold text-gray-900">{emptyTitle}</p>
        <p className="mt-1 text-sm text-gray-600">{emptyDescription}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid={dataTestId}>
      {data.map((booking) => {
        const { date, time } = formatLessonDate(booking.booking_date, booking.start_time);
        const inProgress = isInProgress(booking);
        const displayStatus = inProgress ? 'IN_PROGRESS' : booking.status;
        const status = STATUS_LABELS[displayStatus] ?? booking.status ?? 'Pending';
        const badgeClasses =
          STATUS_STYLES[displayStatus] ?? 'bg-gray-100 text-gray-700';
        const studentName =
          booking.student?.first_name && booking.student?.last_name
            ? `${booking.student.first_name} ${booking.student.last_name}`
            : booking.student?.first_name ?? 'Student';
        const instructorName = booking.instructor
          ? `${booking.instructor.first_name}${booking.instructor.last_initial ? ` ${booking.instructor.last_initial}.` : ''}`
          : 'You';
        const showActionButtons = needsAction(booking) && (onComplete !== undefined || onNoShow !== undefined);

        const isClickable = onViewDetails !== undefined;

        return (
          <Card
            key={booking.id}
            className={`rounded-xl border border-gray-200 bg-white p-4 shadow-sm${isClickable ? ' cursor-pointer transition-shadow hover:shadow-lg' : ''}`}
            data-testid="booking-card"
            {...(isClickable ? { onClick: () => onViewDetails(booking.id) } : {})}
          >
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className={`rounded-full px-3 py-1 text-xs font-medium ${badgeClasses}`}>
                    {status}
                  </span>
                  <span className="text-gray-500">{booking.service_name}</span>
                </div>
                <p className="mt-2 text-lg font-semibold text-gray-900">
                  {studentName}
                </p>
              </div>
              <div className="flex items-start gap-3">
                <div className="text-right text-sm font-medium text-gray-900">
                  {booking.total_price ? (
                    <Fragment>${Number(booking.total_price).toFixed(2)}</Fragment>
                  ) : (
                    <span className="text-gray-500">Pending rate</span>
                  )}
                </div>
                {isClickable && (
                  <ChevronRight className="h-5 w-5 shrink-0 text-gray-400" />
                )}
              </div>
            </div>
            <div className="mt-4 grid gap-4 text-sm text-gray-600 sm:grid-cols-2">
              <div className="flex items-center gap-2">
                <CalendarDays className="h-4 w-4 text-gray-400" />
                <span>{date}</span>
              </div>
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-gray-400" />
                <span>{time}</span>
              </div>
              <div className="flex items-center gap-2">
                <User className="h-4 w-4 text-gray-400" />
                <span>{instructorName}</span>
              </div>
            </div>
            {booking.join_opens_at && (
              <div className="mt-3" onClick={(e) => e.stopPropagation()}>
                <JoinLessonButton
                  bookingId={booking.id}
                  joinOpensAt={booking.join_opens_at}
                  joinClosesAt={booking.join_closes_at}
                />
              </div>
            )}
            {/* Action buttons for past CONFIRMED bookings */}
            {showActionButtons && (
              <div className="mt-4 border-t border-gray-100 pt-4" onClick={(e) => e.stopPropagation()}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-amber-700">
                    <AlertTriangle className="h-4 w-4" />
                    <span className="text-sm font-medium">Action Required</span>
                  </div>
                  <div className="flex gap-2">
                    {onComplete !== undefined && (
                      <button
                        type="button"
                        onClick={() => onComplete(booking.id)}
                        disabled={isActionPending}
                        className="inline-flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="mark-complete-button"
                      >
                        <CheckCircle className="h-4 w-4" />
                        Mark Complete
                      </button>
                    )}
                    {onNoShow !== undefined && (
                      <button
                        type="button"
                        onClick={() => onNoShow(booking.id)}
                        disabled={isActionPending}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-amber-400 px-3 py-1.5 text-sm font-medium text-amber-600 hover:border-amber-500 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50"
                        data-testid="report-no-show-button"
                      >
                        <AlertTriangle className="h-4 w-4" />
                        Report No-Show
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </Card>
        );
      })}
    </div>
  );
}
