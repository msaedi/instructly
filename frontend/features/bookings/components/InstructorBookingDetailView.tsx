import type { ReactNode } from 'react';
import Link from 'next/link';
import { AlertTriangle, Calendar, Clock, MapPin, Monitor } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import type { BookingResponse, InstructorBookingResponse } from '@/features/shared/api/types';
import { shortenBookingId } from '@/lib/bookingId';
import { formatBookingLocationDetail } from '@/lib/bookingLocation';
import { formatPrice } from '@/lib/price';
import { formatStudentDisplayName } from '@/lib/studentName';
import { formatSessionDuration, formatSessionTime } from '@/lib/time/videoSession';
import { cn } from '@/lib/utils';
import { BookingStatusBadge } from './BookingStatusBadge';
import {
  type BookingStatusDisplay,
  formatBookingCreatedDate,
  formatBookingLongDate,
  formatBookingTimeRange,
  formatDurationMinutes,
  formatPlainLabel,
} from './bookingDisplay';

type InstructorBookingDetailViewProps = {
  booking: BookingResponse | InstructorBookingResponse;
  displayStatus: BookingStatusDisplay;
  onMessageStudent: () => Promise<void> | void;
  isMessagePending: boolean;
  isPastLesson: boolean;
  showJoinLesson: boolean;
  isJoinLessonActive: boolean;
  joinCountdownText: string | null;
  showActionRequired: boolean;
  onMarkComplete: () => Promise<void> | void;
  onReportNoShow: () => void;
  canReportNoShow: boolean;
  isActionPending: boolean;
  showReportIssueLink: boolean;
  onReportIssue: () => Promise<void> | void;
  showCancelDiscussionLink: boolean;
  onRequestCancellation: () => Promise<void> | void;
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

function DetailRow({
  icon,
  value,
  className,
  valueClassName,
  dataTestId,
}: {
  icon: ReactNode;
  value: string;
  className?: string;
  valueClassName?: string;
  dataTestId?: string;
}) {
  return (
    <div
      className={cn(
        'flex items-start gap-2 text-sm font-medium text-gray-900 dark:text-gray-100',
        className,
      )}
      data-testid={dataTestId}
    >
      <span className="mt-0.5 shrink-0">{icon}</span>
      <span className={cn('min-w-0 break-words', valueClassName)}>{value}</span>
    </div>
  );
}

export function InstructorBookingDetailView(props: InstructorBookingDetailViewProps) {
  const {
    booking,
    displayStatus,
    onMessageStudent,
    isMessagePending,
    showJoinLesson,
    isJoinLessonActive,
    joinCountdownText,
    showActionRequired,
    onMarkComplete,
    onReportNoShow,
    canReportNoShow,
    isActionPending,
    showReportIssueLink,
    onReportIssue,
    showCancelDiscussionLink,
    onRequestCancellation,
  } = props;
  const studentName = formatStudentDisplayName(
    booking.student.first_name,
    getStudentLastInitial(booking.student),
  );
  const payoutSummary = getPayoutStatusSummary(booking);
  const isOnlineBooking = booking.location_type === 'online';
  const isOnlineLocationHighlighted =
    isOnlineBooking && booking.status === 'CONFIRMED' && isJoinLessonActive;
  const locationValue = isOnlineBooking
    ? 'Online lesson'
    : formatBookingLocationDetail(
        booking.location_type,
        booking.location_address,
        booking.meeting_location,
        booking.service_area,
      );
  const showBottomLinks = showReportIssueLink || showCancelDiscussionLink;
  const showPostPricingSection = showActionRequired || showBottomLinks;

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
            <BookingStatusBadge status={displayStatus} className="self-start" />
          </div>
        </div>

        <div className="px-6">
          <Separator className={sectionDividerClassName} />
        </div>

        <div className="space-y-6 px-6 py-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="space-y-1">
              <p className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                {studentName}
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400">{booking.service_name}</p>
            </div>

            <div
              className="flex flex-wrap items-center justify-end gap-3 self-start"
              data-testid="booking-card-actions"
            >
              {showJoinLesson ? (
                isJoinLessonActive ? (
                  <Link
                    href={`/lessons/${booking.id}`}
                    data-testid="join-lesson-button"
                    className="inline-flex min-w-[116px] cursor-pointer items-center justify-center rounded-full bg-(--color-brand) px-4 py-2 text-sm font-medium text-white shadow-[0_8px_18px_rgba(126,34,206,0.18)] transition-opacity hover:opacity-95 focus-visible:outline-none "
                  >
                    Join lesson
                  </Link>
                ) : (
                  <div className="flex flex-col items-start gap-1">
                    <button
                      type="button"
                      disabled
                      data-testid="join-lesson-button"
                      className="inline-flex min-w-[116px] cursor-not-allowed items-center justify-center rounded-full bg-[#F3F4F6] px-4 py-2 text-sm font-medium text-[#9CA3AF]"
                    >
                      Join lesson
                    </button>
                    {joinCountdownText ? (
                      <p
                        className="text-xs text-gray-500 dark:text-gray-400 tabular-nums"
                        data-testid="join-lesson-countdown"
                        aria-live="polite"
                      >
                        Join opens in {joinCountdownText}
                      </p>
                    ) : null}
                  </div>
                )
              ) : null}

              <Button
                type="button"
                variant="outline"
                size="sm"
                className="min-w-[108px] rounded-full border-(--color-brand) bg-white text-(--color-brand) hover:bg-(--color-brand-lavender) hover:text-(--color-brand)  dark:border-[#A78BFA] dark:bg-transparent dark:text-[#C4B5FD] dark:hover:bg-[#2D174D]/40 dark:hover:text-[#E9D5FF]"
                onClick={onMessageStudent}
                disabled={isMessagePending}
              >
                {isMessagePending ? 'Opening...' : 'Message'}
              </Button>
            </div>
          </div>

          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <DetailRow
                icon={<Calendar className="h-4 w-4 text-gray-400 dark:text-gray-500" />}
                value={formatBookingLongDate(booking.booking_date, booking.start_time)}
              />
              <DetailRow
                icon={<Clock className="h-4 w-4 text-gray-400 dark:text-gray-500" />}
                value={formatBookingTimeRange(
                  booking.booking_date,
                  booking.start_time,
                  booking.end_time,
                )}
              />
            </div>

            <DetailRow
              icon={
                isOnlineBooking ? (
                  <Monitor
                    className={cn(
                      'h-4 w-4',
                      isOnlineLocationHighlighted
                        ? 'text-(--color-brand)'
                        : 'text-gray-400 dark:text-gray-500',
                    )}
                  />
                ) : (
                  <MapPin className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                )
              }
              value={locationValue}
              {...(isOnlineLocationHighlighted
                ? { valueClassName: 'text-(--color-brand)' }
                : {})}
              dataTestId="booking-location-row"
            />
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div
              data-testid="pricing-tile-rate"
              className="rounded-xl p-4 dark:bg-[#2D174D]/40"
              style={{ backgroundColor: '#FAF5FF' }}
            >
              <p className="text-sm text-gray-500 dark:text-gray-400">Rate</p>
              <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                {formatPrice(booking.hourly_rate)}/hr
              </p>
            </div>

            <div
              data-testid="pricing-tile-duration"
              className="rounded-xl p-4 dark:bg-[#2D174D]/40"
              style={{ backgroundColor: '#FAF5FF' }}
            >
              <p className="text-sm text-gray-500 dark:text-gray-400">Duration</p>
              <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                {formatDurationMinutes(booking.duration_minutes)}
              </p>
            </div>

            <div
              data-testid="pricing-tile-lesson-price"
              className="rounded-xl p-4 dark:bg-[#2D174D]/40"
              style={{ backgroundColor: '#FAF5FF' }}
            >
              <p className="text-sm text-gray-500 dark:text-gray-400">Lesson price</p>
              <p className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-100">
                {formatPrice(booking.total_price)}
              </p>
            </div>
          </div>

          {showPostPricingSection ? (
            <div className="space-y-4">
              <Separator className={sectionDividerClassName} />

              {showActionRequired ? (
                <div
                  className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
                  data-testid="booking-action-row"
                >
                  <div className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                    <AlertTriangle className="h-4 w-4 text-gray-400 dark:text-gray-500" />
                    <span>Action required · Did the lesson occur?</span>
                  </div>

                  <div className="flex flex-wrap items-center justify-end gap-3">
                    <Button
                      type="button"
                      onClick={onMarkComplete}
                      disabled={isActionPending}
                      className="rounded-full bg-(--color-brand) px-5 text-white hover:opacity-95 dark:bg-(--color-brand)"
                    >
                      Mark complete
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={onReportNoShow}
                      disabled={isActionPending || !canReportNoShow}
                      className="rounded-full border-red-600 px-5 text-red-600 hover:bg-red-50 hover:text-red-700 disabled:opacity-50 dark:border-red-400 dark:text-red-400 dark:hover:bg-red-950/20 dark:hover:text-red-300"
                    >
                      Report no-show
                    </Button>
                  </div>
                </div>
              ) : null}

              {showBottomLinks ? (
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
                  {showReportIssueLink ? (
                    <button
                      type="button"
                      data-testid="report-issue-link"
                      onClick={onReportIssue}
                      className="text-gray-400 transition-colors hover:text-gray-500"
                    >
                      Report an issue
                    </button>
                  ) : (
                    <span />
                  )}

                  {showCancelDiscussionLink ? (
                    <button
                      type="button"
                      data-testid="cancel-lesson-link"
                      onClick={onRequestCancellation}
                      className="text-gray-400 transition-colors hover:text-gray-500"
                    >
                      I need to cancel this lesson
                    </button>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}

          {booking.status === 'COMPLETED' && payoutSummary ? (
            <div className="rounded-xl border border-gray-200 px-4 py-3 text-sm dark:border-gray-700">
              <p className="font-medium text-gray-900 dark:text-gray-100">Payout status</p>
              <p className="mt-1 text-gray-600 dark:text-gray-400">{payoutSummary}</p>
            </div>
          ) : null}
        </div>

        {booking.video_session_duration_seconds != null ? (
          <div className="space-y-3 px-6 pb-5">
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Video Session
            </p>
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
        ) : null}

        {booking.student_note || booking.instructor_note ? (
          <div className="space-y-4 px-6 pb-5">
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
        ) : null}

        {booking.status === 'CANCELLED' && booking.cancellation_reason ? (
          <div className="space-y-2 px-6 pb-5">
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
        ) : null}
      </Card>
    </div>
  );
}
