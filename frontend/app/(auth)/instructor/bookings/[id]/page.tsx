"use client";

import { useState } from 'react';
import { useParams } from 'next/navigation';
import { AlertTriangle, Calendar } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useCompleteBooking, useBooking, useMarkBookingNoShow } from '@/src/api/services/bookings';
import { useCreateConversation } from '@/hooks/useCreateConversation';
import { queryKeys } from '@/src/api/queryKeys';
import { InstructorBookingDetailView } from '@/features/bookings/components/InstructorBookingDetailView';
import { formatStudentDisplayName } from '@/lib/studentName';
import type { BookingResponse, InstructorBookingResponse } from '@/features/shared/api/types';
import { InstructorDashboardShell } from '@/components/dashboard/InstructorDashboardShell';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';

type InstructorBookingDetail = BookingResponse | InstructorBookingResponse;

type BookingStudentWithLastInitial = InstructorBookingDetail['student'] & {
  last_initial?: string | null;
};

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

export default function BookingDetailsPage() {
  const params = useParams();
  const bookingId = params['id'] as string;
  const queryClient = useQueryClient();
  const [showNoShowModal, setShowNoShowModal] = useState(false);

  const { data: booking, isLoading, error: queryError } = useBooking(bookingId);
  const completeBooking = useCompleteBooking();
  const markNoShow = useMarkBookingNoShow();
  const { createConversation, isCreating: isMessagePending } = useCreateConversation();

  const handleMarkComplete = async () => {
    try {
      await completeBooking.mutateAsync({ bookingId });
      toast.success('Lesson marked as complete', { duration: 3000 });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch {
      toast.error('Failed to mark lesson as complete', { duration: 4000 });
    }
  };

  const handleMarkNoShow = async () => {
    try {
      await markNoShow.mutateAsync({
        bookingId,
        data: { no_show_type: 'student' },
      });
      toast.success('Lesson marked as no-show', { duration: 3000 });
      setShowNoShowModal(false);
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch {
      toast.error('Failed to mark lesson as no-show', { duration: 4000 });
    }
  };

  const handleMessageStudent = async () => {
    if (!booking) {
      return;
    }

    try {
      await createConversation(booking.student.id, { navigateToMessages: true });
    } catch {
      toast.error('Failed to open messages', { duration: 4000 });
    }
  };

  const isPastLesson = (): boolean => {
    if (!booking) {
      return false;
    }

    const lessonEnd = new Date(`${booking.booking_date}T${booking.end_time}`);
    return lessonEnd < new Date();
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

  const studentName = formatStudentDisplayName(
    booking.student.first_name,
    getStudentLastInitial(booking.student),
  );
  const needsAction = booking.status === 'CONFIRMED' && isPastLesson();
  const isActionPending = completeBooking.isPending || markNoShow.isPending;

  return (
    <>
      <InstructorDashboardShell activeNavKey="bookings">
        <BookingsPageHeader />
        <InstructorBookingDetailView
          booking={booking}
          onMessageStudent={handleMessageStudent}
          isMessagePending={isMessagePending}
          needsAction={needsAction}
          onMarkComplete={handleMarkComplete}
          onReportNoShow={() => setShowNoShowModal(true)}
          isActionPending={isActionPending}
        />
      </InstructorDashboardShell>

      {showNoShowModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg dark:bg-gray-800">
            <div className="mb-4">
              <div className="mb-2 flex items-center gap-2 text-amber-600">
                <AlertTriangle className="h-6 w-6" />
                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                  Report No-Show
                </h3>
              </div>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Are you sure you want to mark this lesson as a no-show? This indicates that
                <span className="font-medium"> {studentName || 'the student'}</span> did not
                attend the scheduled lesson.
              </p>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                The student will still be charged for the lesson.
              </p>
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                className="rounded-lg border px-4 py-2 text-sm font-medium transition-colors hover:bg-gray-50 dark:hover:bg-gray-700"
                onClick={() => setShowNoShowModal(false)}
                disabled={markNoShow.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleMarkNoShow}
                disabled={markNoShow.isPending}
              >
                {markNoShow.isPending ? 'Marking...' : 'Confirm No-Show'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
