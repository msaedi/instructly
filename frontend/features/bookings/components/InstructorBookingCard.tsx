import { useRouter } from 'next/navigation';
import { HourglassLow } from '@phosphor-icons/react';
import { AlertTriangle, Calendar, Clock, MapPin } from 'lucide-react';
import { Card } from '@/components/ui/card';
import type { InstructorBookingResponse } from '@/features/shared/api/types';
import { formatBookingLocationLabel } from '@/lib/bookingLocation';
import { formatStudentDisplayName } from '@/lib/studentName';
import { BookingStatusBadge } from './BookingStatusBadge';
import {
  formatBookingCardDate,
  formatBookingTimeRange,
  formatDurationWithService,
} from './bookingDisplay';
import {
  getInstructorBookingDisplayStatus,
  getInstructorBookingEndTime,
} from './instructorBookingDisplayStatus';

type InstructorBookingCardRequiredFields = Pick<
  InstructorBookingResponse,
  | 'id'
  | 'booking_date'
  | 'start_time'
  | 'end_time'
  | 'status'
  | 'service_name'
  | 'duration_minutes'
  | 'location_type'
  | 'location_address'
  | 'meeting_location'
  | 'booking_end_utc'
  | 'no_show_reported_at'
  | 'student'
>;

type InstructorBookingCardOptionalFields = Partial<
  Pick<InstructorBookingResponse, 'lesson_timezone' | 'booking_start_utc'>
>;

export type InstructorBookingCardBooking =
  InstructorBookingCardRequiredFields & InstructorBookingCardOptionalFields;

type InstructorBookingCardProps = {
  booking: InstructorBookingCardBooking;
};

const detailItemClassName = 'flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400';
const detailIconClassName = 'h-4 w-4 shrink-0 text-gray-400 dark:text-gray-500';
const GENERIC_LOCATION_LABELS = new Set([
  "at instructor's location",
  'instructor address shared after booking confirmation',
]);

function isGenericLocationLabel(value: string): boolean {
  return GENERIC_LOCATION_LABELS.has(value.trim().toLowerCase());
}

export function InstructorBookingCard({ booking }: InstructorBookingCardProps) {
  const router = useRouter();
  const studentName = formatStudentDisplayName(
    booking.student.first_name,
    booking.student.last_initial,
  );
  const locationAddress =
    typeof booking.location_address === 'string' ? booking.location_address.trim() : '';
  const meetingLocation =
    typeof booking.meeting_location === 'string' ? booking.meeting_location.trim() : '';
  const resolvedMappableAddress = [locationAddress, meetingLocation].find(
    (value) => value.length > 0 && !isGenericLocationLabel(value),
  );
  const locationLabel =
    booking.location_type === 'online'
      ? formatBookingLocationLabel(booking.location_type)
      : resolvedMappableAddress ?? formatBookingLocationLabel(booking.location_type);
  const locationMapHref =
    booking.location_type !== 'online' && resolvedMappableAddress
      ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(resolvedMappableAddress)}`
      : null;
  const bookingEndTime = getInstructorBookingEndTime(booking);
  const displayStatus = getInstructorBookingDisplayStatus(booking);
  const needsAction =
    booking.status === 'CONFIRMED' &&
    booking.no_show_reported_at == null &&
    bookingEndTime !== null &&
    bookingEndTime <= new Date();
  const bookingDetailHref = `/instructor/bookings/${booking.id}`;
  const openBookingDetail = () => {
    router.push(bookingDetailHref);
  };

  return (
    <div
      role="link"
      tabIndex={0}
      aria-label={`View lesson details for ${studentName}`}
      className="group block cursor-pointer rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
      onClick={openBookingDetail}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          openBookingDetail();
        }
      }}
    >
      <Card
        className="overflow-hidden border-gray-200 shadow-none transition-colors group-hover:border-gray-300 dark:border-gray-700 dark:group-hover:border-gray-600"
        data-testid="booking-card"
      >
        <div>
          <div className="px-5 py-4">
            <div
              className="flex items-start justify-between gap-3"
              data-testid="booking-card-header"
            >
              <p className="flex-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                {studentName}
              </p>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <BookingStatusBadge status={displayStatus} className="shrink-0" />
                {needsAction ? (
                  <span
                    data-testid="booking-action-needed-badge"
                    className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700 dark:bg-amber-950/30 dark:text-amber-300"
                  >
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Action needed
                  </span>
                ) : null}
              </div>
            </div>
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
                <HourglassLow className={detailIconClassName} weight="regular" />
                <span>
                  {formatDurationWithService(booking.duration_minutes, booking.service_name)}
                </span>
              </div>

              <div className={detailItemClassName}>
                <MapPin className={detailIconClassName} />
                {locationMapHref ? (
                  <a
                    href={locationMapHref}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="transition-colors hover:text-(--color-brand-dark)"
                    data-testid="booking-location-link"
                    onClick={(event) => {
                      event.stopPropagation();
                    }}
                    onKeyDown={(event) => {
                      event.stopPropagation();
                    }}
                  >
                    {locationLabel}
                  </a>
                ) : (
                  <span>{locationLabel}</span>
                )}
              </div>
            </div>
          </div>

          <div className="border-t border-gray-100 dark:border-gray-800" />

          <div className="flex justify-end px-5 py-4 text-sm font-medium text-(--color-brand) transition-colors group-hover:text-[#6D28D9] dark:text-[#C4B5FD] dark:group-hover:text-[#DDD6FE]">
            <span>Lesson details ›</span>
          </div>
        </div>
      </Card>
    </div>
  );
}
