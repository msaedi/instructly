'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useLessonDetails } from '@/hooks/useMyLessons';
import { format } from 'date-fns';
import { ArrowLeft, Calendar, Clock, DollarSign, MapPin, MessageCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { InstructorInfo } from '@/components/lessons/InstructorInfo';
import { RescheduleModal } from '@/components/lessons/modals/RescheduleModal';
import { CancelWarningModal } from '@/components/lessons/modals/CancelWarningModal';
import { ChatModal } from '@/components/chat/ChatModal';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { isApiError } from '@/lib/react-query/api';
import { StatusBadge } from '@/components/ui/status-badge';
import UserProfileDropdown from '@/components/UserProfileDropdown';

export default function LessonDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const lessonId = params.id as string;
  const { isAuthenticated, isLoading: isAuthLoading, redirectToLogin, user } = useAuth();

  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);
  const [showChatModal, setShowChatModal] = useState(false);

  const { data: lesson, isLoading, error } = useLessonDetails(lessonId);

  // Redirect to login if not authenticated
  useEffect(() => {
    if (!isAuthLoading && !isAuthenticated) {
      redirectToLogin(`/student/lessons/${lessonId}`);
    }
  }, [isAuthLoading, isAuthenticated, redirectToLogin, lessonId]);

  // Handle 401 errors by redirecting to login
  useEffect(() => {
    if (error && isApiError(error) && error.status === 401) {
      redirectToLogin(`/student/lessons/${lessonId}`);
    }
  }, [error, redirectToLogin, lessonId]);

  // Show loading while checking auth
  if (isAuthLoading) {
    return <LessonDetailsLoading />;
  }

  // Don't render content if not authenticated
  if (!isAuthenticated) {
    return null;
  }

  if (isLoading) {
    return <LessonDetailsLoading />;
  }

  if (error || !lesson) {
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
          <Card className="p-8 text-center bg-white rounded-xl border border-gray-200">
            <p className="text-lg text-gray-600 mb-4">Unable to load lesson details</p>
            <Button
              onClick={() => router.push('/student/lessons')}
              className="bg-purple-700 hover:bg-purple-800 text-white"
            >
              Back to My Lessons
            </Button>
          </Card>
        </div>
      </div>
    );
  }

  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const isUpcoming = lesson.status === 'CONFIRMED';
  const isCompleted = lesson.status === 'COMPLETED';

  const formattedDate = format(lessonDateTime, 'EEEE, MMMM d, yyyy');
  const formattedTime = format(lessonDateTime, 'h:mm a');

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
        {/* Back Button */}
        <div className="mb-6">
          <Button
            variant="ghost"
            onClick={() => router.push('/student/lessons')}
            className="flex items-center gap-2 text-gray-600 hover:text-gray-700"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to My Lessons
          </Button>
        </div>

        {/* Main Content */}
        <Card className="p-6 sm:p-8 bg-white rounded-xl border border-gray-200">
          {/* Lesson Title and Status */}
          <div className="mb-6">
            <div className="flex items-start justify-between">
              <h1 className="text-2xl sm:text-3xl font-bold text-purple-700">
                {lesson.service_name}
              </h1>
              {isCompleted && (
                <StatusBadge variant="success" label="Completed" showIcon={true} />
              )}
            </div>
          </div>

        {/* Date, Time, Price */}
        <div className="space-y-3 mb-6">
          <div className="flex items-center gap-3">
            <Calendar className="h-5 w-5 text-gray-500" />
            <span className="text-lg text-gray-700">{formattedDate}</span>
          </div>
          <div className="flex items-center gap-3">
            <Clock className="h-5 w-5 text-gray-500" />
            <span className="text-lg text-gray-700">{formattedTime}</span>
          </div>
          <div className="flex items-center gap-3">
            <DollarSign className="h-5 w-5 text-gray-500" />
            <span className="text-lg text-gray-700">${lesson.total_price.toFixed(2)}</span>
          </div>
        </div>

        {/* Instructor Info */}
        <div className="mb-6">
          <InstructorInfo instructor={lesson.instructor} />
        </div>

        {/* Action Buttons */}
        <div className="mb-8">
          {isUpcoming && null}
          {isCompleted && (
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={() => router.push(`/instructors/${lesson.instructor_id}`)}
                className="bg-purple-700 hover:bg-purple-800 text-white border-transparent rounded-lg py-2.5 px-6 text-sm font-medium"
              >
                Book Again
              </Button>
              <Button
                onClick={() => router.push(`/student/review/${lesson.id}`)}
                className="bg-white text-purple-700 border-2 border-purple-700 hover:bg-purple-50 rounded-lg py-2.5 px-6 text-sm font-medium"
              >
                Review & tip
              </Button>
              <Button
                onClick={() => setShowChatModal(true)}
                className="bg-white text-gray-400 border-2 border-gray-300 hover:bg-gray-50 rounded-lg py-2.5 px-6 text-sm font-medium"
              >
                <MessageCircle className="h-4 w-4 mr-1" />
                Chat history
              </Button>
            </div>
          )}
        </div>

        <Separator />

        {/* Lesson Details Section */}
        <div className="mt-8 space-y-6">
          <div>
            <h2 className="text-xl font-semibold mb-4 text-gray-700">Lesson Details</h2>

            {/* Location */}
            <div className="mb-4">
              <h3 className="font-medium mb-2 text-gray-600">Location</h3>
              {lesson.meeting_location ? (
                <>
                  <p className="text-gray-500">{lesson.meeting_location}</p>
                  {isUpcoming && (
                    <Button
                      variant="link"
                      className="px-0 h-auto text-purple-700 hover:text-purple-800"
                      onClick={() => console.log('View map')}
                    >
                      <MapPin className="h-4 w-4 mr-1" />
                      View map
                    </Button>
                  )}
                </>
              ) : (
                <p className="text-gray-500">{lesson.service_area || 'NYC'}</p>
              )}
            </div>

            {/* Notes */}
            {(lesson.student_note || lesson.instructor_note) && (
              <div>
                <h3 className="font-medium mb-2 text-gray-600">Description</h3>
                <p className="text-gray-500">
                  {lesson.student_note || lesson.instructor_note}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Manage Booking Section for Upcoming */}
        {isUpcoming && (
          <>
            <Separator className="my-8" />
            <div>
              <h2 className="text-xl font-semibold mb-4 text-gray-700">Manage Booking</h2>
              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={() => setShowRescheduleModal(true)}
                  className="flex-1 sm:flex-initial bg-purple-700 hover:bg-purple-800 text-white border-transparent rounded-lg py-2.5 px-6 text-sm font-medium"
                >
                  Reschedule lesson
                </Button>
                <Button
                  onClick={() => setShowCancelModal(true)}
                  variant="outline"
                  className="flex-1 sm:flex-initial bg-white text-red-600 border-2 border-red-600 hover:bg-red-50 rounded-lg py-2.5 px-6 text-sm font-medium"
                >
                  Cancel lesson
                </Button>
              </div>
            </div>
          </>
        )}

        {/* Receipt Section for Completed */}
        {isCompleted && (
          <>
            <Separator className="my-8" />
            <div>
              <h2 className="text-xl font-semibold mb-4 text-gray-700">Receipt</h2>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-gray-500">Date of Lesson</span>
                  <span className="text-gray-700">{format(lessonDateTime, 'EEE MMM d')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">
                    ${lesson.hourly_rate.toFixed(2)}/hr x {lesson.duration_minutes / 60} hr
                  </span>
                  <span className="text-gray-700">${lesson.total_price.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Platform Fee</span>
                  <span className="text-gray-700">${(lesson.total_price * 0.15).toFixed(2)}</span>
                </div>
                <Separator />
                <div className="flex justify-between font-semibold text-gray-900">
                  <span>Total</span>
                  <span>${(lesson.total_price * 1.15).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-gray-500">
                  <span>Paid</span>
                  <span>${(lesson.total_price * 1.15).toFixed(2)}</span>
                </div>
                <p className="text-xs text-gray-500 pt-2">
                  For cancellations between 12–24 hours before a lesson, you’ll be charged and receive a platform credit for the amount.
                </p>
              </div>
            </div>
          </>
        )}
        </Card>

        {/* Modals */}
        {lesson && (
          <>
            <RescheduleModal
              isOpen={showRescheduleModal}
              onClose={() => setShowRescheduleModal(false)}
              lesson={lesson}
            />
            <CancelWarningModal
              isOpen={showCancelModal}
              onClose={() => setShowCancelModal(false)}
              lesson={lesson}
              onReschedule={() => {
                setShowCancelModal(false);
                setShowRescheduleModal(true);
              }}
            />
            {user && lesson.instructor && (
              <ChatModal
                isOpen={showChatModal}
                onClose={() => setShowChatModal(false)}
                bookingId={lesson.id}
                currentUserId={user.id}
                currentUserName={user.first_name}
                otherUserName={lesson.instructor.first_name || 'Instructor'}
                lessonTitle={lesson.service_name}
                lessonDate={format(new Date(`${lesson.booking_date}T${lesson.start_time}`), 'MMM d, yyyy')}
                isReadOnly={isCompleted}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function LessonDetailsLoading() {
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
        <div className="flex items-center mb-6">
          <Skeleton className="h-10 w-32" />
        </div>
        <Card className="p-6 sm:p-8 bg-white rounded-xl border border-gray-200">
          <Skeleton className="h-8 w-48 mb-6" />
          <div className="space-y-3 mb-6">
            <Skeleton className="h-6 w-64" />
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-6 w-32" />
          </div>
          <Skeleton className="h-20 w-full mb-8" />
          <Skeleton className="h-10 w-32" />
        </Card>
      </div>
    </div>
  );
}
