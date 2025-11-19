import { Card } from '@/components/ui/card';
import { format } from 'date-fns';
import { CalendarDays, Clock, User } from 'lucide-react';
import { Fragment } from 'react';

export type BookingListItem = {
  id: string;
  booking_date: string;
  start_time: string;
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
};

type BookingListProps = {
  data: BookingListItem[];
  isLoading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  'data-testid'?: string;
};

const STATUS_LABELS: Record<string, string> = {
  CONFIRMED: 'Confirmed',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
  NO_SHOW: 'No-show',
};

const STATUS_STYLES: Record<string, string> = {
  CONFIRMED: 'bg-emerald-50 text-emerald-700',
  COMPLETED: 'bg-blue-50 text-blue-700',
  CANCELLED: 'bg-rose-50 text-rose-700',
  NO_SHOW: 'bg-amber-50 text-amber-800',
};

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
        const status = STATUS_LABELS[booking.status] ?? booking.status ?? 'Pending';
        const badgeClasses =
          STATUS_STYLES[booking.status] ?? 'bg-gray-100 text-gray-700';
        const studentName =
          booking.student?.first_name && booking.student?.last_name
            ? `${booking.student.first_name} ${booking.student.last_name}`
            : booking.student?.first_name ?? 'Student';
        const instructorName = booking.instructor
          ? `${booking.instructor.first_name}${booking.instructor.last_initial ? ` ${booking.instructor.last_initial}.` : ''}`
          : 'You';

        return (
          <Card
            key={booking.id}
            className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm"
            data-testid="booking-card"
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
              <div className="text-right text-sm font-medium text-gray-900">
                {booking.total_price ? (
                  <Fragment>${Number(booking.total_price).toFixed(2)}</Fragment>
                ) : (
                  <span className="text-gray-500">Pending rate</span>
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
          </Card>
        );
      })}
    </div>
  );
}
