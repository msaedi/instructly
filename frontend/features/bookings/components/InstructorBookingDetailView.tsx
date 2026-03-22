import type { ReactNode } from 'react';
import {
  AlertTriangle,
  Calendar,
  CheckCircle,
  Clock,
  MapPin,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import type { BookingResponse, InstructorBookingResponse } from '@/features/shared/api/types';
import { formatBookingLocationDetail } from '@/lib/bookingLocation';
import { formatPrice } from '@/lib/price';
import { formatStudentDisplayName } from '@/lib/studentName';
import { formatSessionDuration, formatSessionTime } from '@/lib/time/videoSession';
import { BookingStatusBadge } from './BookingStatusBadge';
import {
  formatBookingCreatedDate,
  formatBookingLongDate,
  formatBookingTimeRange,
  formatDurationMinutes,
  formatDurationWithService,
  formatPlainLabel,
} from './bookingDisplay';
import { shortenBookingId } from '@/lib/bookingId';

type InstructorBookingDetailViewProps = {
  booking: BookingResponse | InstructorBookingResponse;
  onMessageStudent: () => Promise<void> | void;
  isMessagePending: boolean;
  needsAction: boolean;
  onMarkComplete: () => Promise<void> | void;
  onReportNoShow: () => void;
  isActionPending: boolean;
};

type BookingDetail = BookingResponse | InstructorBookingResponse;
const sectionDividerClassName = 'bg-gray-200 dark:bg-gray-700';

type StudentWithLastInitial = BookingDetail['student'] & {
  last_initial?: string | null;
};

function getStudentLastInitial(student: BookingDetail['student']): string {
  const studentWithLastInitial = student as StudentWithLastInitial;
  return studentWithLastInitial.last_initial ?? '';
}

function getPayoutStatusSummary(booking: BookingDetail): string | null {
  const parts = [
    booking.settlement_outcome ? formatPlainLabel(booking.settlement_outcome) : null,
    typeof booking.instructor_payout_amount === 'number'
      ? `${formatPrice(booking.instructor_payout_amount)} payout`
      : null,
  ].filter((value): value is string => value !== null);

  return parts.length > 0 ? parts.join(' · ') : null;
}

function DetailBlock({
  label,
  icon,
  value,
}: {
  label: string;
  icon: ReactNode;
  value: string;
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <div className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-100">
        {icon}
        <span>{value}</span>
      </div>
    </div>
  );
}

export function InstructorBookingDetailView({
  booking,
  onMessageStudent,
  isMessagePending,
  needsAction,
  onMarkComplete,
  onReportNoShow,
  isActionPending,
}: InstructorBookingDetailViewProps) {
  const studentName = formatStudentDisplayName(
    booking.student.first_name,
    getStudentLastInitial(booking.student),
  );
  const payoutSummary = getPayoutStatusSummary(booking);

  return (
    <div className="mt-6">
      <Card className="overflow-hidden border-gray-200 shadow-none dark:border-gray-700">
        <div className="px-6 py-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1">
              <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100">
                Booking #{shortenBookingId(booking.id)}
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Created on {formatBookingCreatedDate(booking.created_at)}
              </p>
            </div>
            <BookingStatusBadge status={booking.status} className="self-start" />
          </div>
        </div>

        <div className="px-6">
          <Separator className={sectionDividerClassName} />
        </div>

        <div className="px-6 py-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1">
              <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100">{studentName}</p>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                {formatDurationWithService(booking.duration_minutes, booking.service_name)}
              </p>
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              className="min-w-[108px] rounded-full"
              onClick={onMessageStudent}
              disabled={isMessagePending}
            >
              {isMessagePending ? 'Opening...' : 'Message'}
            </Button>
          </div>
        </div>

        <div className="px-6">
          <Separator className={sectionDividerClassName} />
        </div>

        <div className="space-y-6 px-6 py-5">
          <div className="grid gap-6 md:grid-cols-2">
            <DetailBlock
              label="Date"
              icon={<Calendar className="h-4 w-4 text-gray-400 dark:text-gray-500" />}
              value={formatBookingLongDate(booking.booking_date, booking.start_time)}
            />
            <DetailBlock
              label="Time"
              icon={<Clock className="h-4 w-4 text-gray-400 dark:text-gray-500" />}
              value={formatBookingTimeRange(booking.booking_date, booking.start_time, booking.end_time)}
            />
          </div>

          <DetailBlock
            label="Location"
            icon={<MapPin className="h-4 w-4 text-gray-400 dark:text-gray-500" />}
            value={formatBookingLocationDetail(
              booking.location_type,
              booking.meeting_location,
              booking.service_area,
            )}
          />
        </div>

        <div className="px-6">
          <Separator className={sectionDividerClassName} />
        </div>

        <div className="px-6 py-5">
          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-xl bg-gray-50 p-4 dark:bg-gray-900/60">
              <p className="text-sm text-gray-500 dark:text-gray-400">Rate</p>
              <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                {formatPrice(booking.hourly_rate)}/hr
              </p>
            </div>

            <div className="rounded-xl bg-gray-50 p-4 dark:bg-gray-900/60">
              <p className="text-sm text-gray-500 dark:text-gray-400">Duration</p>
              <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                {formatDurationMinutes(booking.duration_minutes)}
              </p>
            </div>

            <div className="rounded-xl bg-gray-50 p-4 dark:bg-gray-900/60">
              <p className="text-sm text-gray-500 dark:text-gray-400">Lesson price</p>
              <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                {formatPrice(booking.total_price)}
              </p>
            </div>
          </div>

          {booking.status === 'COMPLETED' && payoutSummary ? (
            <div className="mt-4 rounded-xl border border-gray-200 px-4 py-3 text-sm dark:border-gray-700">
              <p className="font-medium text-gray-900 dark:text-gray-100">Payout status</p>
              <p className="mt-1 text-gray-600 dark:text-gray-400">{payoutSummary}</p>
            </div>
          ) : null}
        </div>

        {booking.video_session_duration_seconds != null ? (
          <>
            <div className="px-6">
              <Separator className={sectionDividerClassName} />
            </div>
            <div className="space-y-3 px-6 py-5">
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Video Session</p>
              <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                <div className="flex items-center justify-between gap-4">
                  <span>Duration</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">
                    {formatSessionDuration(booking.video_session_duration_seconds)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>You joined</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">
                    {formatSessionTime(booking.video_instructor_joined_at)}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-4">
                  <span>Student joined</span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">
                    {formatSessionTime(booking.video_student_joined_at)}
                  </span>
                </div>
              </div>
            </div>
          </>
        ) : null}

        {booking.student_note || booking.instructor_note ? (
          <>
            <div className="px-6">
              <Separator className={sectionDividerClassName} />
            </div>
            <div className="space-y-4 px-6 py-5">
              {booking.student_note ? (
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Note from student
                  </p>
                  <div className="mt-2 rounded-xl bg-gray-50 p-4 text-sm text-gray-700 dark:bg-gray-900/60 dark:text-gray-300">
                    &quot;{booking.student_note}&quot;
                  </div>
                </div>
              ) : null}

              {booking.instructor_note ? (
                <div>
                  <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    Instructor notes
                  </p>
                  <div className="mt-2 rounded-xl bg-gray-50 p-4 text-sm text-gray-700 dark:bg-gray-900/60 dark:text-gray-300">
                    {booking.instructor_note}
                  </div>
                </div>
              ) : null}
            </div>
          </>
        ) : null}

        {booking.status === 'CANCELLED' && booking.cancellation_reason ? (
          <>
            <div className="px-6">
              <Separator className={sectionDividerClassName} />
            </div>
            <div className="space-y-2 px-6 py-5">
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                Cancellation Details
              </p>
              <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
                <p>
                  <span className="font-medium">Reason:</span> {booking.cancellation_reason}
                </p>
                {booking.cancelled_at ? (
                  <p className="mt-1 text-rose-700 dark:text-rose-300">
                    Cancelled on {formatBookingCreatedDate(booking.cancelled_at)}
                  </p>
                ) : null}
              </div>
            </div>
          </>
        ) : null}

        {needsAction ? (
          <>
            <div className="px-6">
              <Separator className={sectionDividerClassName} />
            </div>
            <div className="px-6 py-5">
              <div className="mb-4 rounded-xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-900/60 dark:bg-amber-950/30">
                <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300">
                  <AlertTriangle className="h-5 w-5" />
                  <span className="font-medium">Action Required</span>
                </div>
                <p className="mt-1 text-sm text-amber-700 dark:text-amber-200">
                  This lesson has ended. Please confirm the outcome.
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button
                  type="button"
                  onClick={onMarkComplete}
                  disabled={isActionPending}
                  className="gap-2 bg-green-600 hover:bg-green-700"
                >
                  <CheckCircle className="h-4 w-4" />
                  Mark Complete
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={onReportNoShow}
                  disabled={isActionPending}
                  className="gap-2 border-amber-400 text-amber-700 hover:bg-amber-50 dark:border-amber-700 dark:text-amber-300 dark:hover:bg-amber-950/30"
                >
                  <AlertTriangle className="h-4 w-4" />
                  Report No-Show
                </Button>
              </div>
            </div>
          </>
        ) : null}
      </Card>
    </div>
  );
}
