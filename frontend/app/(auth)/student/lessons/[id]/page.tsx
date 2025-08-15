'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useLessonDetails, calculateCancellationFee } from '@/hooks/useMyLessons';
import { format } from 'date-fns';
import { ArrowLeft, Calendar, Clock, DollarSign, MapPin, MessageCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { InstructorInfo } from '@/components/lessons/InstructorInfo';
import { RescheduleModal } from '@/components/lessons/modals/RescheduleModal';
import { CancelWarningModal } from '@/components/lessons/modals/CancelWarningModal';
import { useAuth } from '@/features/shared/hooks/useAuth';
import { isApiError } from '@/lib/react-query/api';
import { Breadcrumb } from '@/components/ui/breadcrumb';

export default function LessonDetailsPage() {
  const params = useParams();
  const router = useRouter();
  const lessonId = params.id as string;
  const { isAuthenticated, isLoading: isAuthLoading, redirectToLogin } = useAuth();

  const [showRescheduleModal, setShowRescheduleModal] = useState(false);
  const [showCancelModal, setShowCancelModal] = useState(false);

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
      <div className="container mx-auto px-4 py-8 max-w-4xl">
        <Card className="p-8 text-center">
          <p className="text-lg text-muted-foreground mb-4">Unable to load lesson details</p>
          <Button onClick={() => router.push('/student/lessons')}>Back to My Lessons</Button>
        </Card>
      </div>
    );
  }

  const lessonDateTime = new Date(`${lesson.booking_date}T${lesson.start_time}`);
  const isUpcoming = lesson.status === 'CONFIRMED';
  const isCompleted = lesson.status === 'COMPLETED';

  const formattedDate = format(lessonDateTime, 'EEEE, MMMM d, yyyy');
  const formattedTime = format(lessonDateTime, 'h:mm a');

  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      {/* Breadcrumb */}
      <Breadcrumb
        items={[
          { label: 'Home', href: '/' },
          { label: 'My Lessons', href: '/student/lessons' },
          { label: lesson.service_name },
        ]}
      />

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <Button
          variant="ghost"
          onClick={() => router.push('/student/lessons')}
          className="flex items-center gap-2"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to My Lessons
        </Button>
        {isCompleted && (
          <Button variant="outline" onClick={() => console.log('View receipt')}>
            View receipt
          </Button>
        )}
      </div>

      {/* Main Content */}
      <Card className="p-6 sm:p-8 bg-[#EDE7F6]">
        {/* Lesson Title and Status */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold mb-2">
            {lesson.service_name}
            {isCompleted && ' - COMPLETED'}
          </h1>
        </div>

        {/* Date, Time, Price */}
        <div className="space-y-3 mb-6">
          <div className="flex items-center gap-3">
            <Calendar className="h-5 w-5 text-muted-foreground" />
            <span className="text-lg">{formattedDate}</span>
          </div>
          <div className="flex items-center gap-3">
            <Clock className="h-5 w-5 text-muted-foreground" />
            <span className="text-lg">{formattedTime}</span>
          </div>
          <div className="flex items-center gap-3">
            <DollarSign className="h-5 w-5 text-muted-foreground" />
            <span className="text-lg">{lesson.total_price.toFixed(2)}</span>
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
              <Button onClick={() => console.log('Review & tip')} className="bg-[#6741D9] hover:bg-[#5B4BC3] text-white border-transparent">
                Review & tip
              </Button>
              <Button onClick={() => console.log('Chat history')} className="bg-[#6741D9] hover:bg-[#5B4BC3] text-white border-transparent">
                Chat history
              </Button>
              <Button
                onClick={() => router.push(`/instructors/${lesson.instructor_id}`)}
                className="bg-[#6741D9] hover:bg-[#5B4BC3] text-white"
              >
                Book Again
              </Button>
            </div>
          )}
        </div>

        <Separator />

        {/* Lesson Details Section */}
        <div className="mt-8 space-y-6">
          <div>
            <h2 className="text-xl font-semibold mb-4">Lesson Details</h2>

            {/* Location */}
            <div className="mb-4">
              <h3 className="font-medium mb-2">Location</h3>
              <p className="text-muted-foreground">{lesson.service_area || 'NYC'}</p>
              {lesson.meeting_location && (
                <>
                  <p className="text-muted-foreground">{lesson.meeting_location}</p>
                  {isUpcoming && (
                    <Button
                      variant="link"
                      className="px-0 h-auto text-primary"
                      onClick={() => console.log('View map')}
                    >
                      <MapPin className="h-4 w-4 mr-1" />
                      View map
                    </Button>
                  )}
                </>
              )}
            </div>

            {/* Notes */}
            {(lesson.student_note || lesson.instructor_note) && (
              <div>
                <h3 className="font-medium mb-2">Description</h3>
                <p className="text-muted-foreground">
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
              <h2 className="text-xl font-semibold mb-4">Manage Booking</h2>
              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={() => setShowRescheduleModal(true)}
                  className="flex-1 sm:flex-initial bg-[#6741D9] hover:bg-[#5B4BC3] text-white border-transparent"
                >
                  Reschedule lesson
                </Button>
                <Button
                  onClick={() => setShowCancelModal(true)}
                  variant="outline"
                  className="flex-1 sm:flex-initial text-destructive hover:text-destructive"
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
              <h2 className="text-xl font-semibold mb-4">Receipt</h2>
              <div className="space-y-2">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Date of Lesson</span>
                  <span>{format(lessonDateTime, 'EEE MMM d')}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">
                    {lesson.hourly_rate.toFixed(2)}/hr x {lesson.duration_minutes / 60} hr
                  </span>
                  <span>${lesson.total_price.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Platform Fee</span>
                  <span>${(lesson.total_price * 0.15).toFixed(2)}</span>
                </div>
                <Separator />
                <div className="flex justify-between font-semibold">
                  <span>Total</span>
                  <span>${(lesson.total_price * 1.15).toFixed(2)}</span>
                </div>
                <div className="flex justify-between text-muted-foreground">
                  <span>Paid</span>
                  <span>${(lesson.total_price * 1.15).toFixed(2)}</span>
                </div>
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
        </>
      )}
    </div>
  );
}

function LessonDetailsLoading() {
  return (
    <div className="container mx-auto px-4 py-8 max-w-4xl">
      <div className="flex items-center mb-6">
        <Skeleton className="h-10 w-32" />
      </div>
      <Card className="p-6 sm:p-8">
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
  );
}
