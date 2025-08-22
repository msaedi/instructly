'use client';

import { useState, useEffect, Suspense } from 'react';
import { useCurrentLessons, useCompletedLessons } from '@/hooks/useMyLessons';
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
import type { BookingListResponse, Booking } from '@/types/booking';
import UserProfileDropdown from '@/components/UserProfileDropdown';

function MyLessonsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated, isLoading: isAuthLoading, redirectToLogin, user } = useAuth();

  // Chat modal state
  const [chatModalOpen, setChatModalOpen] = useState(false);
  const [selectedBooking, setSelectedBooking] = useState<Booking | null>(null);

  // Initialize tab from URL or default to 'upcoming'
  const tabFromUrl = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState<'upcoming' | 'history'>(
    tabFromUrl === 'history' ? 'history' : 'upcoming'
  );

  const {
    data: upcomingLessons,
    isLoading: isLoadingUpcoming,
    error: errorUpcoming,
  } = useCurrentLessons();

  const {
    data: historyLessons,
    isLoading: isLoadingHistory,
    error: errorHistory,
  } = useCompletedLessons();

  const isLoading = activeTab === 'upcoming' ? isLoadingUpcoming : isLoadingHistory;
  const error = activeTab === 'upcoming' ? errorUpcoming : errorHistory;
  const lessons =
    activeTab === 'upcoming'
      ? upcomingLessons?.items
      : historyLessons?.items;

  // Update URL when tab changes
  const handleTabChange = (tab: 'upcoming' | 'history') => {
    setActiveTab(tab);
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
  if (isAuthLoading) {
    return (
      <div className="min-h-screen">
        <header className="bg-white/90 backdrop-blur-sm border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between max-w-full">
            <a href="/" className="inline-block">
              <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
            </a>
            <div className="pr-4">
              <div className="animate-pulse">
                <div className="w-10 h-10 bg-gray-200 rounded-full"></div>
              </div>
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
          <a href="/" className="inline-block">
            <h1 className="text-3xl font-bold text-purple-700 hover:text-purple-800 transition-colors cursor-pointer pl-4">iNSTAiNSTRU</h1>
          </a>
          <div className="pr-4">
            <UserProfileDropdown />
          </div>
        </div>
      </header>

      <div className="container mx-auto px-8 lg:px-32 py-8 max-w-6xl">
        {/* Page Header */}
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold text-gray-600">My Lessons</h1>
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
          lessons.map((lesson) => (
            <LessonCard
              key={lesson.id}
              lesson={lesson}
              isCompleted={activeTab === 'history'}
              onViewDetails={() => router.push(`/student/lessons/${lesson.id}`)}
              onChat={() => handleOpenChat(lesson)}
              onBookAgain={() => router.push(`/instructors/${lesson.instructor_id}`)}
              onReviewTip={() => router.push(`/student/review/${lesson.id}`)}
            />
          ))
        ) : (
          // Empty state
          <div className="text-center py-12">
            {activeTab === 'upcoming' ? (
              <>
                <p className="text-lg text-muted-foreground mb-4">
                  You don't have any upcoming lessons
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

      {/* Chat Modal */}
      {selectedBooking && user && selectedBooking.instructor && (
        <ChatModal
          isOpen={chatModalOpen}
          onClose={() => {
            setChatModalOpen(false);
            setSelectedBooking(null);
          }}
          bookingId={selectedBooking.id}
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
