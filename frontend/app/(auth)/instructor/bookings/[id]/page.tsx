"use client";

import { useEffect, useId, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import { Calendar, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useBooking, useMarkBookingNoShow } from '@/src/api/services/bookings';
import { useMarkLessonComplete } from '@/src/api/services/instructor-bookings';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { queryKeys } from '@/src/api/queryKeys';
import { useFocusTrap } from '@/hooks/useFocusTrap';
import { useCountdown } from '@/hooks/useCountdown';
import { InstructorBookingDetailView } from '@/features/bookings/components/InstructorBookingDetailView';
import { formatBookingLongDate } from '@/features/bookings/components/bookingDisplay';
import {
  getInstructorBookingDisplayStatus,
  getInstructorBookingEndTime,
} from '@/features/bookings/components/instructorBookingDisplayStatus';
import { extractUnknownErrorMessage } from '@/lib/apiErrors';
import { logger } from '@/lib/logger';
import type { BookingResponse, InstructorBookingResponse } from '@/features/shared/api/types';
import { InstructorDashboardShell } from '@/components/dashboard/InstructorDashboardShell';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';

type InstructorBookingDetail = BookingResponse | InstructorBookingResponse;

type BookingStudentWithLastInitial = InstructorBookingDetail['student'] & {
  last_initial?: string | null;
  last_name?: string | null;
};

const NO_SHOW_WINDOW_PASSED_MESSAGE =
  'No-show window has passed (24 hours after lesson end).';

function BookingsPageHeader() {
  return (
    <SectionHeroCard
      id="bookings-first-card"
      icon={Calendar}
      title="Bookings"
      subtitle="Track upcoming sessions and review completed lessons all in one place."
    />
  );
}

function getStudentLastInitial(student: InstructorBookingDetail['student']): string {
  const studentWithLastInitial = student as BookingStudentWithLastInitial;
  return studentWithLastInitial.last_initial ?? '';
}

function parseOptionalDate(value?: string | null): Date | null {
  if (!value) {
    return null;
  }

  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function hasNoShowWindowPassed(
  booking: InstructorBookingDetail,
  now: Date = new Date()
): boolean {
  const bookingEndTime = getInstructorBookingEndTime(booking);
  if (bookingEndTime === null) {
    return false;
  }

  return now.getTime() > bookingEndTime.getTime() + 24 * 60 * 60 * 1000;
}

function formatNoShowStudentName(student: InstructorBookingDetail['student']): string {
  const studentWithFallbackLastName = student as BookingStudentWithLastInitial;
  const firstName = studentWithFallbackLastName.first_name?.trim().toUpperCase() || 'STUDENT';
  const explicitLastInitial = getStudentLastInitial(studentWithFallbackLastName)
    .trim()
    .replace(/\.$/, '');
  const fallbackLastInitial = studentWithFallbackLastName.last_name?.trim()?.charAt(0) ?? '';
  const lastInitial = (explicitLastInitial || fallbackLastInitial).toUpperCase();

  return lastInitial ? `${firstName} ${lastInitial}.` : firstName;
}

export default function BookingDetailsPage() {
  const params = useParams();
  const bookingId = params['id'] as string;
  const queryClient = useQueryClient();
  const [showNoShowModal, setShowNoShowModal] = useState(false);
  const [now, setNow] = useState(() => new Date());
  const noShowModalRef = useRef<HTMLDivElement | null>(null);
  const noShowTitleId = useId();

  const { data: booking, isLoading, error: queryError } = useBooking(bookingId);
  const joinOpensCountdown = useCountdown(booking?.join_opens_at ?? null);
  const joinClosesCountdown = useCountdown(booking?.join_closes_at ?? null);
  const completeBooking = useMarkLessonComplete();
  const markNoShow = useMarkBookingNoShow();
  const { createConversation, isCreating: isMessagePending } = useCreateConversation();

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setNow(new Date());
    }, 30_000);

    return () => window.clearInterval(intervalId);
  }, []);

  useFocusTrap({
    isOpen: showNoShowModal,
    containerRef: noShowModalRef,
    onEscape: () => setShowNoShowModal(false),
  });

  const handleMarkComplete = async () => {
    try {
      await completeBooking.mutateAsync({ bookingId, data: {} });
      toast.success('Lesson marked as complete', { duration: 3000 });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch (error) {
      logger.error('Failed to mark lesson as complete', error);
      toast.error('Failed to mark lesson as complete', { duration: 4000 });
    }
  };

  const handleMarkNoShow = async () => {
    if (!booking) {
      return;
    }

    if (hasNoShowWindowPassed(booking, new Date())) {
      setShowNoShowModal(false);
      toast.error(NO_SHOW_WINDOW_PASSED_MESSAGE, { duration: 4000 });
      return;
    }

    try {
      await markNoShow.mutateAsync({
        bookingId,
        data: { no_show_type: 'student' },
      });
      toast.success('Lesson marked as no-show', { duration: 3000 });
      setShowNoShowModal(false);
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch (error) {
      const message =
        extractUnknownErrorMessage(error) ?? 'Failed to mark lesson as no-show';
      logger.error('Failed to mark lesson as no-show', error);
      toast.error(message, { duration: 4000 });
    }
  };

  const openStudentConversation = async (initialMessage?: string) => {
    if (!booking) {
      return;
    }

    try {
      await createConversation(booking.student.id, {
        navigateToMessages: true,
        ...(initialMessage ? { initialMessage } : {}),
      });
    } catch (error) {
      logger.error('Failed to open messages', error);
      toast.error('Failed to open messages', { duration: 4000 });
    }
  };

  const handleMessageStudent = async () => {
    await openStudentConversation();
  };

  if (isLoading) {
    return (
      <InstructorDashboardShell activeNavKey="bookings">
        <BookingsPageHeader />
        <div className="flex min-h-[60vh] items-center justify-center">
          <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-t-2 border-indigo-500" />
        </div>
      </InstructorDashboardShell>
    );
  }

  if (queryError || !booking) {
    return (
      <InstructorDashboardShell activeNavKey="bookings">
        <BookingsPageHeader />
        <div className="mx-auto max-w-4xl px-4 py-8">
          <div className="text-center">
            <p className="mb-4 text-red-600">
              {queryError ? 'Failed to load booking details' : 'Booking not found'}
            </p>
          </div>
        </div>
      </InstructorDashboardShell>
    );
  }

  const lessonDate = formatBookingLongDate(booking.booking_date, booking.start_time);
  const noShowStudentName = formatNoShowStudentName(booking.student);
  const bookingEndTime = getInstructorBookingEndTime(booking);
  const joinOpensAt = parseOptionalDate(booking.join_opens_at);
  const joinClosesAt = parseOptionalDate(booking.join_closes_at);
  const displayStatus = getInstructorBookingDisplayStatus(booking, now);
  const isPastLesson = bookingEndTime !== null && bookingEndTime < now;
  const isOnlineConfirmedBooking =
    booking.location_type === 'online' && booking.status === 'CONFIRMED';
  const showJoinLesson =
    isOnlineConfirmedBooking &&
    joinOpensAt !== null &&
    joinClosesAt !== null &&
    !joinClosesCountdown.isExpired;
  const isJoinLessonActive =
    showJoinLesson &&
    joinOpensCountdown.isExpired &&
    !joinClosesCountdown.isExpired;
  const joinCountdownText =
    showJoinLesson && !isJoinLessonActive ? joinOpensCountdown.formatted : null;
  const showActionRequired =
    booking.status === 'CONFIRMED' && isPastLesson && !booking.no_show_reported_at;
  const showReportIssueLink =
    booking.status !== 'CANCELLED' && booking.status !== 'PAYMENT_FAILED';
  const showCancelDiscussionLink = booking.status === 'CONFIRMED' && !isPastLesson;
  const noShowWindowPassed = hasNoShowWindowPassed(booking, now);
  const canReportNoShow = !noShowWindowPassed;
  const isActionPending = completeBooking.isPending || markNoShow.isPending;

  const reportIssueMessage = `Hi ${booking.student.first_name}, I need to report an issue with our ${booking.service_name} lesson on ${lessonDate}. `;
  const cancelLessonMessage = `Hi ${booking.student.first_name}, I need to discuss cancelling our ${booking.service_name} lesson on ${lessonDate}. `;

  const handleReportIssue = async () => {
    await openStudentConversation(reportIssueMessage);
  };

  const handleCancelDiscussion = async () => {
    await openStudentConversation(cancelLessonMessage);
  };

  const isJoinVisible = showJoinLesson;
  const isJoinActive = isJoinLessonActive;
  const shouldShowActionRequired = showActionRequired;
  const shouldShowReportIssueLink = showReportIssueLink;
  const shouldShowCancelDiscussionLink = showCancelDiscussionLink;
  const shouldAllowNoShow = canReportNoShow;

  return (
    <>
      <InstructorDashboardShell activeNavKey="bookings">
        <BookingsPageHeader />
        <InstructorBookingDetailView
          booking={booking}
          displayStatus={displayStatus}
          onMessageStudent={handleMessageStudent}
          isMessagePending={isMessagePending}
          isPastLesson={isPastLesson}
          showJoinLesson={isJoinVisible}
          isJoinLessonActive={isJoinActive}
          joinCountdownText={joinCountdownText}
          showActionRequired={shouldShowActionRequired}
          onMarkComplete={handleMarkComplete}
          onReportNoShow={() => setShowNoShowModal(true)}
          canReportNoShow={shouldAllowNoShow}
          isActionPending={isActionPending}
          showReportIssueLink={shouldShowReportIssueLink}
          onReportIssue={handleReportIssue}
          showCancelDiscussionLink={shouldShowCancelDiscussionLink}
          onRequestCancellation={handleCancelDiscussion}
        />
      </InstructorDashboardShell>

      {showNoShowModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div
            ref={noShowModalRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={noShowTitleId}
            tabIndex={-1}
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-lg dark:bg-gray-800"
          >
            <div className="flex items-start justify-between gap-4">
              <h3 id={noShowTitleId} className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Report no-show
              </h3>
              <button
                type="button"
                aria-label="Close report no-show modal"
                className="rounded-full p-1 text-(--color-brand) transition-colors hover:bg-[#F5F3FF] focus-visible:outline-none   disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-[#2D174D]/40"
                onClick={() => setShowNoShowModal(false)}
                disabled={markNoShow.isPending}
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <p className="mt-4 text-sm leading-6 text-gray-600 dark:text-gray-300">
              Confirm that <span className="font-semibold text-gray-900 dark:text-gray-100">{noShowStudentName}</span>{' '}
              was a no-show. They will still be charged for the lesson.
            </p>

            <div className="mt-6 flex justify-end">
              <button
                type="button"
                className="rounded-full border border-[#DC2626] px-4 py-2 text-sm font-medium text-[#DC2626] transition-colors hover:bg-red-50 focus-visible:outline-none   disabled:cursor-not-allowed disabled:opacity-50 dark:hover:bg-red-950/20"
                onClick={handleMarkNoShow}
                disabled={markNoShow.isPending || noShowWindowPassed}
              >
                Confirm no-show
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
