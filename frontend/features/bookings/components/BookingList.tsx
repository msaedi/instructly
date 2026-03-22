import type { InstructorBookingResponse } from '@/features/shared/api/types';
import { Card } from '@/components/ui/card';
import { InstructorBookingCard } from './InstructorBookingCard';

export type BookingListItem = Pick<
  InstructorBookingResponse,
  | 'id'
  | 'booking_date'
  | 'start_time'
  | 'end_time'
  | 'status'
  | 'service_name'
  | 'duration_minutes'
  | 'location_type'
  | 'student'
>;

type BookingListProps = {
  data: BookingListItem[];
  isLoading?: boolean;
  emptyTitle: string;
  emptyDescription: string;
  'data-testid'?: string;
};

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
            className="animate-pulse p-4 insta-surface-card"
          >
            <div className="h-4 w-1/3 rounded bg-gray-200 dark:bg-gray-700" />
            <div className="mt-2 h-4 w-1/4 rounded bg-gray-100 dark:bg-gray-700" />
            <div className="mt-4 h-3 w-1/5 rounded bg-gray-100 dark:bg-gray-700" />
          </Card>
        ))}
      </div>
    );
  }

  if (!data || data.length === 0) {
    return (
      <div
        className="rounded-xl border border-dashed border-gray-300 p-6 text-center insta-surface-card"
        data-testid={`${dataTestId}-empty`}
      >
        <div className="space-y-1">
          <p className="text-base font-semibold text-gray-900 dark:text-gray-100">{emptyTitle}</p>
          {emptyDescription ? (
            <p className="text-sm text-gray-600 dark:text-gray-400">{emptyDescription}</p>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid={dataTestId}>
      {data.map((booking) => (
        <InstructorBookingCard key={booking.id} booking={booking} />
      ))}
    </div>
  );
}
