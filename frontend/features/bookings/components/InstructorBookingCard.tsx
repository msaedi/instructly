import Link from 'next/link';
import { Calendar, Clock, Clock3, MapPin } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import type { InstructorBookingResponse } from '@/features/shared/api/types';
import { formatBookingLocationLabel } from '@/lib/bookingLocation';
import { formatStudentDisplayName } from '@/lib/studentName';
import { BookingStatusBadge } from './BookingStatusBadge';
import {
  formatBookingCardDate,
  formatBookingTimeRange,
  formatDurationWithService,
} from './bookingDisplay';

export type InstructorBookingCardBooking = Pick<
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

type InstructorBookingCardProps = {
  booking: InstructorBookingCardBooking;
};

const detailItemClassName = 'flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400';
const detailIconClassName = 'h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500';

export function InstructorBookingCard({ booking }: InstructorBookingCardProps) {
  const studentName = formatStudentDisplayName(
    booking.student.first_name,
    booking.student.last_initial,
  );

  return (
    <Link
      href={`/instructor/bookings/${booking.id}`}
      className="group block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
    >
      <Card
        className="overflow-hidden border-gray-200 shadow-none transition-colors group-hover:border-gray-300 dark:border-gray-700 dark:group-hover:border-gray-600"
        data-testid="booking-card"
      >
        <div className="px-5 py-4">
          <BookingStatusBadge status={booking.status} />
        </div>

        <Separator />

        <div className="px-5 py-4">
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">{studentName}</p>
        </div>

        <div className="px-5 pb-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className={detailItemClassName}>
              <Calendar className={detailIconClassName} />
              <span>{formatBookingCardDate(booking.booking_date, booking.start_time)}</span>
            </div>

            <div className={detailItemClassName}>
              <Clock className={detailIconClassName} />
              <span>
                {formatBookingTimeRange(
                  booking.booking_date,
                  booking.start_time,
                  booking.end_time,
                )}
              </span>
            </div>

            <div className={detailItemClassName}>
              <Clock3 className={detailIconClassName} />
              <span>
                {formatDurationWithService(booking.duration_minutes, booking.service_name)}
              </span>
            </div>

            <div className={detailItemClassName}>
              <MapPin className={detailIconClassName} />
              <span>{formatBookingLocationLabel(booking.location_type)}</span>
            </div>
          </div>
        </div>

        <Separator />

        <div className="flex justify-end px-5 py-4 text-sm font-medium text-gray-700 transition-colors group-hover:text-gray-900 dark:text-gray-300 dark:group-hover:text-gray-100">
          <span>View lesson ›</span>
        </div>
      </Card>
    </Link>
  );
}
