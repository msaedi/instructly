'use client';

import Link from 'next/link';
import { useCallback, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertTriangle, ArrowLeft, Calendar } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import UserProfileDropdown from '@/components/UserProfileDropdown';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { BookingList, type BookingListItem } from '@/features/bookings/components/BookingList';
import type { PaginatedBookingResponse } from '@/features/shared/api/client';
import { useInstructorBookings } from '@/hooks/queries/useInstructorBookings';
import { useCompleteBooking, useMarkBookingNoShow } from '@/src/api/services/bookings';
import { queryKeys } from '@/src/api/queryKeys';

import { useEmbedded } from '../_embedded/EmbeddedContext';

type TabValue = 'upcoming' | 'past';

const TAB_PARAM = 'tab';
const PAGE_SIZE = 50;

const parseTab = (value: string | null): TabValue => (value === 'past' ? 'past' : 'upcoming');

function BookingsPageImpl() {
  const embedded = useEmbedded();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const tabFromUrl = parseTab(searchParams.get(TAB_PARAM));
  const [activeTab, setActiveTab] = useState<TabValue>(tabFromUrl);
  const [noShowModalBookingId, setNoShowModalBookingId] = useState<string | null>(null);

  // Mutations for complete and no-show actions
  const completeBooking = useCompleteBooking();
  const markNoShow = useMarkBookingNoShow();

  const handleTabChange = useCallback(
    (value: TabValue) => {
      setActiveTab(value);
      const nextParams = new URLSearchParams(searchParams.toString());
      nextParams.set(TAB_PARAM, value);
      // Use correct base path depending on whether we're embedded in dashboard
      const basePath = embedded ? '/instructor/dashboard' : '/instructor/bookings';
      router.replace(`${basePath}?${nextParams.toString()}`, { scroll: false });
    },
    [router, searchParams, embedded]
  );

  const upcomingQuery = useInstructorBookings({
    status: 'CONFIRMED',
    upcoming: true,
    page: 1,
    perPage: PAGE_SIZE,
  });

  const pastQuery = useInstructorBookings({
    upcoming: false,
    excludeFutureConfirmed: true,
    page: 1,
    perPage: PAGE_SIZE,
  });

  const pluckBookings = useCallback((payload?: PaginatedBookingResponse): BookingListItem[] => {
    if (!Array.isArray(payload?.items)) return [];
    return payload.items as BookingListItem[];
  }, []);

  const upcomingItems = useMemo(() => pluckBookings(upcomingQuery.data), [pluckBookings, upcomingQuery.data]);
  const pastItems = useMemo(() => pluckBookings(pastQuery.data), [pluckBookings, pastQuery.data]);

  const showLoading = upcomingQuery.isLoading || pastQuery.isLoading;

  // Get the booking data for the no-show modal
  const noShowModalBooking = useMemo(() => {
    if (!noShowModalBookingId) return null;
    return pastItems.find((b) => b.id === noShowModalBookingId) ?? null;
  }, [noShowModalBookingId, pastItems]);

  // Handler for Mark Complete button
  const handleMarkComplete = useCallback(async (bookingId: string) => {
    try {
      await completeBooking.mutateAsync({ bookingId });
      toast.success('Lesson marked as complete', { duration: 3000 });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(bookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch {
      toast.error('Failed to mark lesson as complete', { duration: 4000 });
    }
  }, [completeBooking, queryClient]);

  // Handler for opening the No-Show modal
  const handleNoShowClick = useCallback((bookingId: string) => {
    setNoShowModalBookingId(bookingId);
  }, []);

  // Handler for confirming No-Show in the modal
  const handleConfirmNoShow = useCallback(async () => {
    if (!noShowModalBookingId) return;
    try {
      await markNoShow.mutateAsync({
        bookingId: noShowModalBookingId,
        data: { no_show_type: 'student' },
      });
      toast.success('Lesson marked as no-show', { duration: 3000 });
      setNoShowModalBookingId(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.detail(noShowModalBookingId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.bookings.instructor() });
    } catch {
      toast.error('Failed to mark lesson as no-show', { duration: 4000 });
    }
  }, [noShowModalBookingId, markNoShow, queryClient]);

  const isActionPending = completeBooking.isPending || markNoShow.isPending;

  return (
    <div className="min-h-screen">
      {!embedded && (
        <header className="relative border-b border-gray-200 bg-white px-4 py-4 backdrop-blur-sm sm:px-6">
          <div className="flex max-w-full items-center justify-between">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="pl-0 text-3xl font-bold text-[#7E22CE] transition-colors hover:text-[#7E22CE] sm:pl-4">
                iNSTAiNSTRU
              </h1>
            </Link>
            <div className="pr-0 sm:pr-4">
              <UserProfileDropdown />
            </div>
          </div>
          <div className="pointer-events-none absolute inset-x-0 top-1/2 hidden -translate-y-1/2 sm:block">
            <div className="pointer-events-auto container mx-auto max-w-6xl px-8 lg:px-32">
              <Link href="/instructor/dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
                <ArrowLeft className="h-4 w-4" />
                <span>Back to dashboard</span>
              </Link>
            </div>
          </div>
        </header>
      )}

      <div className={embedded ? 'max-w-none px-0 py-0' : 'container mx-auto max-w-6xl px-8 py-8 lg:px-32'}>
        {!embedded && (
          <div className="mb-2 sm:hidden">
            <Link href="/instructor/dashboard" aria-label="Back to dashboard" className="inline-flex items-center gap-1 text-[#7E22CE]">
              <ArrowLeft className="h-5 w-5" />
              <span className="sr-only">Back to dashboard</span>
            </Link>
          </div>
        )}

        <SectionHeroCard
          id={embedded ? 'bookings-first-card' : undefined}
          icon={Calendar}
          title="Bookings"
          subtitle="Track upcoming sessions and review completed lessons all in one place."
        />

        <div className="mt-6 rounded-lg border border-gray-200 bg-white shadow-sm">
          <div role="tablist" aria-label="Bookings tabs" className="flex border-b border-gray-200">
            {(['upcoming', 'past'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={activeTab === tab}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                  activeTab === tab ? 'border-b-2 border-[#7E22CE] text-[#7E22CE]' : 'text-gray-600 hover:text-[#7E22CE]'
                }`}
                onClick={() => handleTabChange(tab)}
              >
                {tab === 'upcoming' ? 'Upcoming' : 'Past'}
              </button>
            ))}
          </div>
          <div className="p-4 sm:p-6">
            {activeTab === 'upcoming' ? (
              <BookingList
                data={upcomingItems}
                isLoading={showLoading}
                emptyTitle="No upcoming bookings"
                emptyDescription="New lessons will appear here once students confirm."
              />
            ) : (
              <BookingList
                data={pastItems}
                isLoading={showLoading}
                emptyTitle="No past bookings yet"
                emptyDescription="Completed lessons will show up as soon as they finish."
                onComplete={handleMarkComplete}
                onNoShow={handleNoShowClick}
                isActionPending={isActionPending}
              />
            )}
          </div>
        </div>
      </div>

      {/* No-Show Confirmation Modal */}
      {noShowModalBookingId !== null && noShowModalBooking !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-md rounded-lg bg-white p-6 shadow-lg">
            <div className="mb-4">
              <div className="mb-2 flex items-center gap-2 text-amber-600">
                <AlertTriangle className="h-6 w-6" />
                <h3 className="text-lg font-semibold text-gray-900">Report No-Show</h3>
              </div>
              <p className="text-sm text-gray-600">
                Are you sure you want to mark this lesson as a no-show? This indicates that
                <span className="font-medium">
                  {' '}
                  {noShowModalBooking.student?.first_name && noShowModalBooking.student?.last_name
                    ? `${noShowModalBooking.student.first_name} ${noShowModalBooking.student.last_name}`
                    : 'the student'}
                </span>{' '}
                did not attend the scheduled lesson.
              </p>
              <p className="mt-2 text-sm text-gray-500">The student will still be charged for the lesson.</p>
            </div>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                className="rounded-lg border px-4 py-2 text-sm font-medium transition-colors hover:bg-gray-50"
                onClick={() => setNoShowModalBookingId(null)}
                disabled={markNoShow.isPending}
              >
                Cancel
              </button>
              <button
                type="button"
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleConfirmNoShow}
                disabled={markNoShow.isPending}
              >
                {markNoShow.isPending ? 'Marking...' : 'Confirm No-Show'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function InstructorBookingsPage() {
  return <BookingsPageImpl />;
}
