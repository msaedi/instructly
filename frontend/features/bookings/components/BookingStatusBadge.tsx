import { getBookingStatusBadgeClasses } from '@/lib/bookingStatus';
import { cn } from '@/lib/utils';
import type { BookingStatusDisplay } from './bookingDisplay';
import { getBookingStatusLabel } from './bookingDisplay';

type BookingStatusBadgeProps = {
  status: BookingStatusDisplay;
  className?: string;
};

export function BookingStatusBadge({ status, className }: BookingStatusBadgeProps) {
  const normalizedStatus = status ? String(status).toUpperCase() : 'PENDING';

  return (
    <span
      className={cn(
        'inline-flex w-fit items-center rounded-full px-3 py-1 text-xs font-medium',
        getBookingStatusBadgeClasses(normalizedStatus),
        className
      )}
    >
      {getBookingStatusLabel(normalizedStatus)}
    </span>
  );
}
