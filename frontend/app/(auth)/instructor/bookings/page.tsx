'use client';

import Link from 'next/link';
import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ArrowLeft, Calendar } from 'lucide-react';

import UserProfileDropdown from '@/components/UserProfileDropdown';
import { SectionHeroCard } from '@/components/dashboard/SectionHeroCard';
import { BookingList, type BookingListItem } from '@/features/bookings/components/BookingList';
import type { InstructorBookingResponse } from '@/features/shared/api/types';
import { useInstructorBookings } from '@/hooks/queries/useInstructorBookings';
import { getTextWidthTabButtonClasses, getTextWidthTabLabelClasses } from '@/lib/textWidthTabs';

import { useEmbedded } from '../_embedded/EmbeddedContext';

type TabValue = 'upcoming' | 'past';

const TAB_PARAM = 'tab';
const PAGE_SIZE = 50;

type PaginatedInstructorBookings = {
  items: InstructorBookingResponse[];
  total: number;
  page: number;
  per_page: number;
  has_next: boolean;
  has_prev: boolean;
};

const parseTab = (value: string | null): TabValue => (value === 'past' ? 'past' : 'upcoming');

function BookingsPageImpl() {
  const embedded = useEmbedded();
  const router = useRouter();
  const searchParams = useSearchParams();
  const activeTab = parseTab(searchParams.get(TAB_PARAM));

  const handleTabChange = useCallback(
    (value: TabValue) => {
      const nextParams = new URLSearchParams(searchParams.toString());
      nextParams.set(TAB_PARAM, value);
      // Use correct base path depending on whether we're embedded in dashboard
      const basePath = embedded ? '/instructor/dashboard' : '/instructor/bookings';
      router.replace(`${basePath}?${nextParams.toString()}`, { scroll: false });
    },
    [router, searchParams, embedded]
  );

  const upcomingQuery = useInstructorBookings({
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

  const pluckBookings = useCallback((payload?: PaginatedInstructorBookings): BookingListItem[] => {
    if (!Array.isArray(payload?.items)) return [];
    return payload.items as BookingListItem[];
  }, []);

  const upcomingItems = useMemo(() => pluckBookings(upcomingQuery.data), [pluckBookings, upcomingQuery.data]);
  const pastItems = useMemo(() => pluckBookings(pastQuery.data), [pluckBookings, pastQuery.data]);

  const showLoading = activeTab === 'upcoming' ? upcomingQuery.isLoading : pastQuery.isLoading;

  return (
    <div className="min-h-screen insta-dashboard-page">
      {!embedded && (
        <header className="relative px-4 py-4 sm:px-6 insta-dashboard-header">
          <div className="flex max-w-full items-center justify-between">
            <Link href="/instructor/dashboard" className="inline-block">
              <h1 className="pl-0 text-3xl font-bold text-[#7E22CE] transition-colors hover:text-purple-900 dark:hover:text-purple-300 sm:pl-4">
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

        <div className="mt-6 insta-surface-card">
          <div role="tablist" aria-label="Bookings tabs" className="flex border-b border-gray-200 dark:border-gray-700">
            {(['upcoming', 'past'] as const).map((tab) => (
              <button
                key={tab}
                type="button"
                role="tab"
                aria-selected={activeTab === tab}
                className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${getTextWidthTabButtonClasses(activeTab === tab)}`}
                onClick={() => handleTabChange(tab)}
              >
                <span className={getTextWidthTabLabelClasses(activeTab === tab)}>
                  {tab === 'upcoming' ? 'Upcoming' : 'Past'}
                </span>
              </button>
            ))}
          </div>
          <div className="p-4 sm:p-6">
            {activeTab === 'upcoming' ? (
              <BookingList
                data={upcomingItems}
                isLoading={showLoading}
                emptyTitle="No upcoming bookings"
                emptyDescription="New bookings will appear here."
              />
            ) : (
              <BookingList
                data={pastItems}
                isLoading={showLoading}
                emptyTitle="No completed lessons yet"
                emptyDescription="Your completed sessions will appear here."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default function InstructorBookingsPage() {
  return <BookingsPageImpl />;
}
