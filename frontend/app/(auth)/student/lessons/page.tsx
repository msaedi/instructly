'use client';

import { useState, useEffect, Suspense, useMemo, useSyncExternalStore } from 'react';
import Link from 'next/link';
import { useCurrentLessonsInfinite, useCompletedLessonsInfinite } from '@/hooks/useMyLessons';
import { LessonCard } from '@/components/lessons/LessonCard';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { useRouter, useSearchParams } from 'next/navigation';
import { AlertCircle } from 'lucide-react';
import { format } from 'date-fns';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { isApiError } from '@/lib/react-query/api';
import { ChatModal } from '@/components/chat/ChatModal';
import type { Booking } from '@/types/booking';
import UserProfileDropdown from '@/components/UserProfileDropdown';
import { useRatingsBatch, useExistingReviews } from '@/hooks/queries/useReviewsBatch';
import { resolveBookingDateTimes } from '@/lib/timezone/formatBookingTime';
import { JoinLessonButton } from '@/components/lessons/video/JoinLessonButton';

function MyLessonsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, isLoading: isAuthLoading, redirectToLogin, user } = useAuth();

  // Chat modal state
  const [chatModalOpen, setChatModalOpen] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null);
  const hasMounted = useSyncExternalStore(
    () => () => {},
    () => true,
    () => false
  );

  // Initialize tab from URL or default to 'upcoming'
  const tabFromUrl = searchParams.get('tab');
  // Fix hydration by reading URL params directly in initial state
  const [activeTab, setActiveTab] = useState<'upcoming' | 'history'>(() => {
    // This function only runs on the client, avoiding hydration mismatch
    if (typeof window !== 'undefined') {
      return tabFromUrl === 'history' ? 'history' : 'upcoming';
    }
    return 'upcoming';
  });

  type LessonItem = Omit<Booking, 'updated_at'> & { updated_at?: string };

  const {
    data: upcomingLessons,
    isLoading: isLoadingUpcoming,
    isFetchingNextPage: isFetchingUpcoming = false,
    fetchNextPage: fetchUpcomingNextPage = async () => {},
    hasNextPage: hasMoreUpcoming = false,
    error: errorUpcoming,
  } = useCurrentLessonsInfinite();

  const {
    data: historyLessons,
    isLoading: isLoadingHistory,
    isFetchingNextPage: isFetchingHistory = false,
    fetchNextPage: fetchHistoryNextPage = async () => {},
    hasNextPage: hasMoreHistory = false,
    error: errorHistory,
  } = useCompletedLessonsInfinite();

  const combinedLessons = useMemo(() => {
    const items = [
      ...(upcomingLessons?.items ?? []),
      ...(historyLessons?.items ?? []),
    ];
    const deduped = new Map<string, LessonItem>();
    items.forEach((lesson) => {
      deduped.set(String(lesson.id), lesson as LessonItem);
    });
    return Array.from(deduped.values());
  }, [historyLessons?.items, upcomingLessons?.items]);

  const { upcomingList, historyList } = useMemo(() => {
    if (!hasMounted) {
      return {
        upcomingList: upcomingLessons?.items ?? [],
        historyList: historyLessons?.items ?? [],
      };
    }

    const now = new Date();
    const upcoming: LessonItem[] = [];
    const history: LessonItem[] = [];
    const startTimes = new Map<string, number>();

    combinedLessons.forEach((lesson) => {
      const { start, end } = resolveBookingDateTimes(lesson);
      const startMs = start?.getTime() ?? 0;
      startTimes.set(String(lesson.id), startMs);

      if (lesson.status === 'CONFIRMED') {
        if (end && now >= end) {
          history.push(lesson);
        } else {
          upcoming.push(lesson);
        }
        return;
      }

      if (lesson.status === 'COMPLETED' || lesson.status === 'CANCELLED' || lesson.status === 'NO_SHOW') {
        history.push(lesson);
        return;
      }

      history.push(lesson);
    });

    upcoming.sort((a, b) => {
      const aStart = startTimes.get(String(a.id)) ?? 0;
      const bStart = startTimes.get(String(b.id)) ?? 0;
      return aStart - bStart;
    });

    history.sort((a, b) => {
      const aStart = startTimes.get(String(a.id)) ?? 0;
      const bStart = startTimes.get(String(b.id)) ?? 0;
      return bStart - aStart;
    });

    return { upcomingList: upcoming, historyList: history };
  }, [combinedLessons, hasMounted, historyLessons?.items, upcomingLessons?.items]);

  const isLoading = activeTab === 'upcoming'
    ? isLoadingUpcoming && (upcomingLessons?.items?.length ?? 0) === 0
    : isLoadingHistory && (historyLessons?.items?.length ?? 0) === 0;
  const error = activeTab === 'upcoming' ? errorUpcoming : errorHistory;
  const lessons = activeTab === 'upcoming' ? upcomingList : historyList;
  const hasMore = activeTab === 'upcoming' ? hasMoreUpcoming : hasMoreHistory;
  const isFetchingMore = activeTab === 'upcoming'
    ? isFetchingUpcoming
    : isFetchingHistory;

  // Derive instructor IDs for batch ratings lookup
  const uniqueInstructorIds = useMemo(() => {
    const visible = lessons || [];
    return Array.from(new Set(visible.map((l) => l.instructor_id))).filter(Boolean) as string[];
  }, [lessons]);

  // Derive booking IDs that might have reviews (completed or past-confirmed lessons)
  const checkableBookingIds = useMemo(() => {
    const visible = lessons || [];
    const now = new Date();
    return visible
      .filter((l) => {
        if (l.status === 'COMPLETED') return true;
        if (l.status === 'CONFIRMED') {
          const { end } = resolveBookingDateTimes(l);
          return end ? end < now : false;
        }
        return false;
      })
      .map((l) => l.id);
  }, [lessons]);

  // Use React Query hooks for batch data fetching (prevents duplicate API calls)
  const { data: ratingsMap = {} } = useRatingsBatch(uniqueInstructorIds);
  const { data: existingReviewsData } = useExistingReviews(checkableBookingIds);
  const reviewedMap = existingReviewsData?.reviewedMap ?? {};

  // Update URL when tab changes
  const handleTabChange = (tab: 'upcoming' | 'history') => {
    setActiveTab(tab);
    // Store the tab in sessionStorage for navigation back from details
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('lessonsTab', tab);
    }
    router.push(`/student/lessons?tab=${tab}`, { scroll: false });
  };

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthLoading && !isAuthenticated) {
      redirectToLogin('/student/lessons');
    }
  }, [isAuthLoading, isAuthenticated, redirectToLogin]);

  // Handle 401 errors by redirecting to login
  useEffect(() => {
    if (error && isApiError(error) && error.status === 401) {
      redirectToLogin('/student/lessons');
    }
  }, [error, redirectToLogin]);

  // Show loading while checking auth
  if (!hasMounted || isAuthLoading) {
    return (
      <div className="min-h-screen">
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <Link href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </Link>
            <div className="pr-4">
              <UserProfileDropdown />
            </div>
          </div>
        </header>
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
          <Skeleton className="h-8 w-48 mb-8" />
          <Skeleton className="h-12 w-full mb-8" />
          <div className="space-y-4">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
          </div>
        </div>
      </div>
    );
  }

  // Don't render content if not authenticated
  if (!isAuthenticated) {
    return null;
  }

  // Handle opening chat
  const handleOpenChat = (lesson: Booking) => {
    setSelectedBooking(lesson);
    setChatModalOpen(true);
  };

  return (
    <div className="min-h-screen">
      {/* Header - matching other pages */}
      <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
        <div className="flex items-center justify-between max-w-full">
          <Link href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-[#7E22CE] hover:text-[#7E22CE] transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </Link>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header */}
      <div className="flex items-center justify-between mb-8">
        <h1 data-testid="my-lessons-title" className="text-3xl font-bold text-gray-600">My Lessons</h1>
      </div>

      {/* Tabs */}
      <div className="flex gap-4 mb-8 border-b bg-white p-4 rounded-lg">
        <button
          onClick={() => handleTabChange('upcoming')}
          className={`pb-4 px-2 font-medium transition-colors cursor-pointer text-gray-600 hover:text-gray-700 ${
            activeTab === 'upcoming'
              ? 'border-b-2 border-gray-600'
              : ''
          }`}
        >
          Upcoming
        </button>
        <button
          onClick={() => handleTabChange('history')}
          className={`pb-4 px-2 font-medium transition-colors cursor-pointer text-gray-600 hover:text-gray-700 ${
            activeTab === 'history'
              ? 'border-b-2 border-gray-600'
              : ''
          }`}
        >
          History
        </button>
      </div>

      {/* Lessons List */}
      <div className="space-y-4">
        {error ? (
          // Error state
          <Card className="p-8 bg-red-50 border-red-200">
            <div className="flex flex-col items-center text-center space-y-3">
              <AlertCircle className="h-12 w-12 text-red-500" />
              <h3 className="text-lg font-semibold text-red-800">Failed to load lessons</h3>
              <p className="text-red-600">
                There was an error loading your lessons. Please try again.
              </p>
              <Button
                onClick={() => window.location.reload()}
                variant="outline"
                className="cursor-pointer"
              >
                Retry
              </Button>
            </div>
          </Card>
        ) : isLoading ? (
          // Loading skeleton
          <>
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
          </>
        ) : lessons && lessons.length > 0 ? (
          // Lesson cards
          lessons.map((lesson) => {
            const { start, end } = resolveBookingDateTimes(lesson);
            const now = new Date();
            const isInProgress =
              hasMounted &&
              lesson.status === 'CONFIRMED' &&
              start !== null &&
              end !== null &&
              now >= start &&
              now < end;
            const isCompleted =
              lesson.status === 'COMPLETED' ||
              (lesson.status === 'CONFIRMED' && hasMounted && end !== null && now >= end);
            const br = ratingsMap[lesson.instructor_id];

            return (
              <LessonCard
                key={lesson.id}
                lesson={{ ...lesson, updated_at: (lesson as unknown as { updated_at?: string }).updated_at ?? new Date().toISOString() } as unknown as Booking}
                isCompleted={isCompleted}
                isInProgress={isInProgress}
                onViewDetails={() => router.push(`/student/lessons/${lesson.id}`)}
                onChat={() => handleOpenChat(lesson as unknown as Booking)}
                onBookAgain={() => router.push(`/instructors/${lesson.instructor_id}`)}
                onReviewTip={() => router.push(`/student/review/${lesson.id}`)}
                {...(typeof br?.rating === 'number' && { prefetchedRating: br.rating })}
                {...(typeof br?.review_count === 'number' && { prefetchedReviewCount: br.review_count })}
                prefetchedReviewed={!!reviewedMap[lesson.id]}
                suppressFetchRating={true}
                suppressFetchReviewed={true}
              >
                {lesson.join_opens_at && (
                  <JoinLessonButton
                    bookingId={lesson.id}
                    joinOpensAt={lesson.join_opens_at}
                    joinClosesAt={lesson.join_closes_at}
                  />
                )}
              </LessonCard>
            );
          })
        ) : (
          // Empty state
          <div className="text-center py-12">
            {activeTab === 'upcoming' ? (
              <>
                <p className="text-lg text-muted-foreground mb-4">
                  You don&apos;t have any upcoming lessons
                </p>
                <p className="text-muted-foreground">Ready to learn something new?</p>
              </>
            ) : (
              <>
                <p className="text-lg text-muted-foreground mb-4">
                  Your lesson history will appear here
                </p>
                <p className="text-muted-foreground">
                  This includes completed, cancelled, and past lessons.
                </p>
              </>
            )}
          </div>
        )}
      </div>

      {lessons && lessons.length > 0 && hasMore && !error && (
        <div className="flex justify-center pt-6">
          <Button
            onClick={() => {
              if (activeTab === 'upcoming') {
                void fetchUpcomingNextPage();
              } else {
                void fetchHistoryNextPage();
              }
            }}
            variant="ghost"
            className="w-full max-w-sm rounded-lg py-3 text-purple-600 hover:bg-purple-50"
            disabled={isFetchingMore}
          >
            {isFetchingMore ? 'Loading...' : 'Load More Lessons'}
          </Button>
        </div>
      )}

      {/* Chat Modal */}
      {selectedBooking && user && selectedBooking.instructor && (
        <ChatModal
          isOpen={chatModalOpen}
          onClose={() => {
            setChatModalOpen(false);
            setSelectedBooking(null);
          }}
          bookingId={selectedBooking.id}
          instructorId={selectedBooking.instructor_id}
          currentUserId={user.id}
          currentUserName={user.first_name}
          otherUserName={selectedBooking.instructor.first_name || 'Instructor'}
          lessonTitle={selectedBooking.service_name}
          lessonDate={format(new Date(`${selectedBooking.booking_date}T${selectedBooking.start_time}`), 'MMM d, yyyy')}
          isReadOnly={activeTab === 'history'}
        />
      )}
      </div>
    </div>
  );
}

export default function MyLessonsPage() {
  return (
    <Suspense
      fallback={
        <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
          <Skeleton className="h-8 w-48 mb-8" />
          <Skeleton className="h-12 w-full mb-8" />
          <div className="space-y-4">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-48 w-full" />
          </div>
        </div>
      }
    >
      <MyLessonsContent />
    </Suspense>
  );
}
